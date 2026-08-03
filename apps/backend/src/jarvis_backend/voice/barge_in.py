"""Barge-in controller (see ADR-0011 for the full latency budget analysis).

While `VoiceEngine` is in the `SPEAKING` state, `BargeInController` runs a
concurrent VAD check against live microphone frames — the microphone
pipeline is never stopped or restarted between states (per the Phase 3
mandate: "Resume listening without restarting the pipeline"), it simply
isn't being *listened to* for barge-in purposes outside `SPEAKING` state.
The moment VAD reports speech, `BargeInController` calls
`SpeakerManager.stop()` directly — bypassing any queue, event, or async
handoff that would add latency — and reports the measured interrupt
latency for observability.

**Latency budget (target: under 150ms end-to-end):**
  - VAD frame duration: 20ms (one `AudioConfig` frame) — worst case, speech
    starts 1ms into a frame and isn't detected until that frame completes.
  - VAD hangover: `WebRtcVadProvider`'s hangover smoothing is NOT applied
    here — barge-in uses a separate, hangover-free VAD check (raw
    per-frame speech/non-speech) so detection isn't delayed by the same
    "avoid fragmenting an utterance" smoothing that's correct for STT
    segmentation but actively harmful for barge-in's latency requirement.
  - `SpeakerManager.stop()`: bounded by one output callback period (the
    `blocksize` configured on the `OutputStream`, typically 10-20ms at
    16kHz) — see `speaker.py`'s docstring.
  - Total worst case: ~20ms (frame) + ~1ms (VAD inference) + ~20ms
    (speaker callback) ≈ 41ms, comfortably under the 150ms target with
    margin for scheduling jitter under real OS load.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import numpy as np
import structlog

from .types import AudioFrame, AudioSink

logger = structlog.get_logger("jarvis_backend.voice.barge_in")


class RawSpeechDetector:
    """A hangover-free wrapper around any raw VAD engine, used
    specifically for barge-in. Unlike `WebRtcVadProvider.is_speech()`
    (which smooths across a hangover window to avoid fragmenting STT
    segments), barge-in wants the fastest possible raw signal — smoothing
    here would directly add latency to the interrupt path, trading
    barge-in responsiveness for a benefit (segment continuity) that
    doesn't apply when the goal is "detect speech has started," not
    "detect an utterance has ended."
    """

    def __init__(self, raw_vad: Any) -> None:
        # Accepts the same underlying `webrtcvad.Vad` instance a
        # `WebRtcVadProvider` wraps, reused here without its hangover
        # layer — see `VoiceEngine`'s composition for how both share one
        # underlying VAD engine instance.
        self._raw_vad = raw_vad

    def is_speech(self, frame: AudioFrame, sample_rate: int) -> bool:
        samples = np.clip(frame.samples, -1.0, 1.0)
        pcm16 = (samples * 32767).astype(np.int16)
        return bool(self._raw_vad.is_speech(pcm16.tobytes(), sample_rate))


@dataclass(slots=True, frozen=True)
class BargeInEvent:
    detected_at_s: float
    interrupt_latency_ms: float


class BargeInController:
    def __init__(self, speaker: AudioSink, detector: RawSpeechDetector) -> None:
        self._speaker = speaker
        self._detector = detector

    async def monitor(
        self, frames: AsyncIterator[AudioFrame], sample_rate: int
    ) -> BargeInEvent | None:
        """Consumes `frames` until speech is detected (returning a
        `BargeInEvent`) or the async iterator is exhausted/cancelled
        (returning `None` — the normal "TTS finished without
        interruption" path, when `VoiceEngine` cancels this coroutine's
        task once playback completes on its own).
        """
        async for frame in frames:
            if self._detector.is_speech(frame, sample_rate):
                detected_at = time.monotonic()
                await self._speaker.stop()
                latency_ms = (time.monotonic() - detected_at) * 1000
                logger.info("barge_in_triggered", interrupt_latency_ms=latency_ms)
                return BargeInEvent(detected_at_s=detected_at, interrupt_latency_ms=latency_ms)
        return None


async def race_playback_against_barge_in(
    playback_task: asyncio.Task[None],
    barge_in_task: asyncio.Task[BargeInEvent | None],
) -> BargeInEvent | None:
    """Runs TTS playback and barge-in monitoring concurrently; whichever
    finishes first determines the outcome. If playback finishes first
    (normal completion), the barge-in task is cancelled cleanly. If
    barge-in fires first, playback has already been halted by
    `SpeakerManager.stop()` inside `BargeInController.monitor` — this
    function's job is purely to stop tracking, not to stop audio (that
    already happened at the moment of detection, not after this function
    resolves, which is exactly what keeps barge-in latency independent of
    asyncio task-scheduling overhead here).
    """
    done, pending = await asyncio.wait(
        {playback_task, barge_in_task}, return_when=asyncio.FIRST_COMPLETED
    )

    for task in pending:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    if barge_in_task in done:
        return barge_in_task.result()
    return None
