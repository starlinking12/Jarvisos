"""Barge-in controller for low-latency interruption during TTS playback."""

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
    """Hangover-free speech detector used specifically by barge-in."""

    def __init__(self, raw_vad: Any) -> None:
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
        """Return an interruption event when speech is detected, otherwise None."""
        async for frame in frames:
            if self._detector.is_speech(frame, sample_rate):
                detected_at = time.monotonic()
                await self._speaker.stop()
                latency_ms = (time.monotonic() - detected_at) * 1000
                logger.info("barge_in_triggered", interrupt_latency_ms=latency_ms)
                return BargeInEvent(detected_at_s=detected_at, interrupt_latency_ms=latency_ms)
        return None


async def _cancel_and_wait(task: asyncio.Task[Any]) -> None:
    if task.done():
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def race_playback_against_barge_in(
    playback_task: asyncio.Task[None],
    barge_in_task: asyncio.Task[BargeInEvent | None],
) -> BargeInEvent | None:
    """Race TTS playback against speech detection without orphaning either task.

    A barge-in monitor can end naturally when a finite/test microphone source is
    exhausted. ``None`` from that monitor is not a winner: playback continues.
    An actual ``BargeInEvent`` wins a same-tick tie with playback completion.
    """
    done, _ = await asyncio.wait(
        {playback_task, barge_in_task}, return_when=asyncio.FIRST_COMPLETED
    )

    if barge_in_task in done:
        try:
            barge_in_event = barge_in_task.result()
        except BaseException:
            await _cancel_and_wait(playback_task)
            raise

        if barge_in_event is not None:
            await _cancel_and_wait(playback_task)
            return barge_in_event

        if playback_task.done():
            return None

        await playback_task
        return None

    await _cancel_and_wait(barge_in_task)
    return None
