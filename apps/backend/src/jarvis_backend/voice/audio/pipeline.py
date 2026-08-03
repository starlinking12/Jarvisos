"""Audio streaming pipeline.

Composes `MicrophoneManager.frames()` with a `VadProvider` to produce two
higher-level streams `VoiceEngine` consumes: a continuous frame stream
(for wake-word detection, which runs on every frame regardless of speech
activity) and discrete speech segments (start-of-speech to end-of-speech,
for STT, which only needs to run on actual utterances). Centralizing this
here means wake-word and STT logic never duplicate VAD-driven segmentation.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import numpy as np
import structlog

from ..types import AudioConfig, AudioFrame, AudioSamples, AudioSource
from ..vad.provider import VadProvider

logger = structlog.get_logger("jarvis_backend.voice.audio.pipeline")


@dataclass(slots=True)
class SpeechSegment:
    """One complete utterance: concatenated samples from VAD-detected
    speech start to speech end, ready for STT."""

    samples: AudioSamples
    config: AudioConfig
    start_s: float
    end_s: float


@dataclass(slots=True)
class _SegmentAccumulator:
    frames: list[AudioSamples] = field(default_factory=list)
    start_s: float | None = None


class AudioStreamingPipeline:
    """Wraps an `AudioSource` (typically `MicrophoneManager`, or a fake
    satisfying the same protocol in tests) with VAD-based speech
    segmentation. Every frame is yielded from `frames()` (for wake-word, which must see
    silence too — it's listening for a word, not for "any speech"); a
    `SpeechSegment` is yielded from `segments()` only once VAD detects a
    complete utterance (for STT, which should not be invoked on silence or
    non-speech noise, per the project's performance/latency mandate).
    """

    def __init__(self, microphone: AudioSource, vad: VadProvider) -> None:
        self._microphone = microphone
        self._vad = vad

    async def frames(self) -> AsyncIterator[AudioFrame]:
        async for frame in self._microphone.frames():
            yield frame

    async def segments(self) -> AsyncIterator[SpeechSegment]:
        accumulator = _SegmentAccumulator()

        async for frame in self._microphone.frames():
            is_speech = self._vad.is_speech(frame)

            if is_speech:
                if accumulator.start_s is None:
                    accumulator.start_s = frame.timestamp_s
                    logger.debug("speech_segment_started", timestamp_s=frame.timestamp_s)
                accumulator.frames.append(frame.samples)
            elif accumulator.start_s is not None:
                # Speech just ended — VAD provider decides how much
                # trailing silence constitutes "the utterance is over"
                # (its own hangover/debounce logic); once it reports
                # non-speech, the pipeline finalizes the segment.
                segment = SpeechSegment(
                    samples=np.concatenate(accumulator.frames),
                    config=frame.config,
                    start_s=accumulator.start_s,
                    end_s=frame.timestamp_s,
                )
                logger.debug(
                    "speech_segment_ended",
                    duration_s=segment.end_s - segment.start_s,
                    sample_count=len(segment.samples),
                )
                yield segment
                accumulator = _SegmentAccumulator()
