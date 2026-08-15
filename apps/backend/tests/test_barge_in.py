from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import numpy as np

from jarvis_backend.voice.barge_in import (
    BargeInController,
    BargeInEvent,
    RawSpeechDetector,
    race_playback_against_barge_in,
)
from jarvis_backend.voice.types import AudioConfig, AudioFrame


class _FakeRawVad:
    def __init__(self, speech_after_call: int | None = None) -> None:
        self.speech_after_call = speech_after_call
        self.call_count = 0

    def is_speech(self, pcm_bytes: bytes, sample_rate: int) -> bool:
        del pcm_bytes, sample_rate
        self.call_count += 1
        if self.speech_after_call is None:
            return False
        return self.call_count >= self.speech_after_call


class _FakeSpeaker:
    def __init__(self) -> None:
        self.stop_called = False

    async def stop(self) -> None:
        self.stop_called = True


def _make_frame() -> AudioFrame:
    return AudioFrame(
        samples=np.zeros(320, dtype=np.float32), config=AudioConfig(), timestamp_s=0.0
    )


async def _frame_stream(count: int) -> AsyncIterator[AudioFrame]:
    for _ in range(count):
        yield _make_frame()


async def test_raw_speech_detector_reports_speech_from_underlying_vad() -> None:
    detector = RawSpeechDetector(_FakeRawVad(speech_after_call=1))
    assert detector.is_speech(_make_frame(), 16_000) is True


async def test_raw_speech_detector_reports_silence() -> None:
    detector = RawSpeechDetector(_FakeRawVad(speech_after_call=None))
    assert detector.is_speech(_make_frame(), 16_000) is False


async def test_barge_in_controller_stops_speaker_on_detected_speech() -> None:
    speaker = _FakeSpeaker()
    detector = RawSpeechDetector(_FakeRawVad(speech_after_call=2))
    controller = BargeInController(speaker, detector)  # type: ignore[arg-type]
    event = await controller.monitor(_frame_stream(5), sample_rate=16_000)
    assert event is not None
    assert speaker.stop_called is True
    assert event.interrupt_latency_ms >= 0


async def test_barge_in_controller_returns_none_if_stream_exhausted_without_speech() -> None:
    speaker = _FakeSpeaker()
    detector = RawSpeechDetector(_FakeRawVad(speech_after_call=None))
    controller = BargeInController(speaker, detector)  # type: ignore[arg-type]
    event = await controller.monitor(_frame_stream(3), sample_rate=16_000)
    assert event is None
    assert speaker.stop_called is False


async def test_race_returns_none_when_playback_finishes_first() -> None:
    async def fast_playback() -> None:
        await asyncio.sleep(0.01)

    async def slow_barge_in() -> BargeInEvent | None:
        await asyncio.sleep(10)
        return None

    playback_task = asyncio.create_task(fast_playback())
    barge_in_task = asyncio.create_task(slow_barge_in())
    result = await race_playback_against_barge_in(playback_task, barge_in_task)
    assert result is None
    assert barge_in_task.cancelled()


async def test_race_returns_event_when_barge_in_fires_first() -> None:
    async def slow_playback() -> None:
        await asyncio.sleep(10)

    expected_event = BargeInEvent(detected_at_s=0.0, interrupt_latency_ms=5.0)

    async def fast_barge_in() -> BargeInEvent | None:
        await asyncio.sleep(0.01)
        return expected_event

    playback_task = asyncio.create_task(slow_playback())
    barge_in_task = asyncio.create_task(fast_barge_in())
    result = await race_playback_against_barge_in(playback_task, barge_in_task)
    assert result is expected_event
    assert playback_task.cancelled()


async def test_race_keeps_playback_when_barge_in_stream_exhausts() -> None:
    playback_finished = False

    async def playback() -> None:
        nonlocal playback_finished
        await asyncio.sleep(0.01)
        playback_finished = True

    async def exhausted_barge_in() -> BargeInEvent | None:
        return None

    playback_task = asyncio.create_task(playback())
    barge_in_task = asyncio.create_task(exhausted_barge_in())

    result = await race_playback_against_barge_in(playback_task, barge_in_task)

    assert result is None
    assert playback_finished is True
    assert playback_task.done()
    assert not playback_task.cancelled()
