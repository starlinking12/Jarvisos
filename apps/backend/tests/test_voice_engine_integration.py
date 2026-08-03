"""VoiceEngine integration tests.

Every hardware- or native-dependency-backed component (microphone,
speaker, VAD, wake word, STT, TTS) is faked here, satisfying the same
`AudioSource`/`AudioSink`/`VadProvider`/`WakeWordProvider`/`SttProvider`/
`TtsProvider` protocols the real providers do — this is exactly what
"hardware-independent CI tests" means per the Phase 3 mandate, and is the
direct payoff of `VoiceEngine`/`AudioStreamingPipeline` depending on
protocols rather than concrete hardware classes (see `voice/types.py`).

The `Orchestrator` used here is real (not faked) — built from the same
`conftest.py` fixtures Phase 2's tests use, backed by `MockProvider` — so
these tests also exercise the genuine Voice Engine ↔ Orchestrator
integration end to end, not a stubbed-out response.

Each `SpeechSegment` in these tests requires one trailing non-speech
frame after the "spoken" frames so `FakeVad` reports end-of-speech and
`AudioStreamingPipeline.segments()` closes the segment — every
`listening_frames` list below is constructed as N speech frames + 1
trailing silence frame, and `FakeVad`'s `speech_frame_count` is set to
N (one less than the batch's total length) accordingly.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import numpy as np
from jarvis_contracts import JarvisEvent

from jarvis_backend.agents.orchestrator import Orchestrator
from jarvis_backend.agents.safety_gate import PermissionDecisionKind
from jarvis_backend.agents.safety_gate import PermissionScope as BackendPermissionScope
from jarvis_backend.agents.safety_gate import SafetyGate, SafetyPolicy
from jarvis_backend.event_bus import EventBus
from jarvis_backend.voice.audio.pipeline import AudioStreamingPipeline, SpeechSegment
from jarvis_backend.voice.barge_in import BargeInController
from jarvis_backend.voice.types import (
    AudioConfig,
    AudioFrame,
    TranscriptSegment,
    VoiceProfile,
    VoiceState,
    WakeWordDetection,
)
from jarvis_backend.voice.voice_engine import VoiceEngine


def _permissive_safety_gate() -> SafetyGate:
    """VoiceEngine.start() gates on `audio.microphone` — conftest's shared
    `safety_gate` fixture is default-deny (correct for Phase 2's
    production-safety tests), so this test file builds its own
    microphone-permissive gate instead of importing that fixture."""
    return SafetyGate(
        SafetyPolicy(
            default=PermissionDecisionKind.DENY,
            overrides={BackendPermissionScope.AUDIO_MICROPHONE: PermissionDecisionKind.ALLOW},
        )
    )


def _frame(value: float = 0.0) -> AudioFrame:
    return AudioFrame(
        samples=np.full(320, value, dtype=np.float32), config=AudioConfig(), timestamp_s=0.0
    )


class FakeMicrophone:
    """Serves pre-scripted frame batches, one batch per call to
    `frames()` — VoiceEngine's sequential state machine calls
    `frames()`/`pipeline.segments()` fresh once per phase, so scripting by
    call order maps directly onto scripting by phase (wake-word frames,
    then listening frames, then barge-in-monitoring frames)."""

    def __init__(self, frame_batches: list[list[AudioFrame]]) -> None:
        self._batches = frame_batches
        self._call_index = 0

    def frames(self) -> AsyncIterator[AudioFrame]:
        batch = self._batches[self._call_index] if self._call_index < len(self._batches) else []
        self._call_index += 1
        return self._iter(batch)

    @staticmethod
    async def _iter(batch: list[AudioFrame]) -> AsyncIterator[AudioFrame]:
        for frame in batch:
            yield frame

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


class FakeSpeaker:
    def __init__(self) -> None:
        self.played_frames: list[AudioFrame] = []
        self.stop_called = False
        self.started = False
        self.closed = False

    async def start(self) -> None:
        self.started = True

    async def play(self, frame: AudioFrame) -> None:
        self.played_frames.append(frame)

    async def stop(self) -> None:
        self.stop_called = True

    async def wait_until_idle(self) -> None:
        return None

    async def close(self) -> None:
        self.closed = True


class FakeVad:
    """Speech for the first `speech_frame_count` frames it sees, then
    silence — enough to make `AudioStreamingPipeline.segments()` yield
    exactly one `SpeechSegment` when the input batch has one trailing
    silence frame beyond that count."""

    def __init__(self, speech_frame_count: int) -> None:
        self._speech_frame_count = speech_frame_count
        self._seen = 0

    def is_speech(self, frame: AudioFrame) -> bool:
        self._seen += 1
        return self._seen <= self._speech_frame_count


class FakeWakeWord:
    def __init__(self, detect_on_frame_index: int) -> None:
        self._detect_on = detect_on_frame_index
        self._seen = 0

    def process(self, frame: AudioFrame) -> WakeWordDetection | None:
        self._seen += 1
        if self._seen == self._detect_on:
            return WakeWordDetection(wake_word="jarvis", confidence=0.95, timestamp_s=0.0)
        return None

    def reset(self) -> None:
        self._seen = 0


class FakeStt:
    def __init__(self, final_text: str) -> None:
        self._final_text = final_text

    async def stream_transcribe(
        self, segment: SpeechSegment
    ) -> AsyncIterator[TranscriptSegment]:
        yield TranscriptSegment(
            text=self._final_text.split(" ")[0],
            is_final=False,
            confidence=None,
            start_s=0.0,
            end_s=0.1,
        )
        yield TranscriptSegment(
            text=self._final_text,
            is_final=True,
            confidence=None,
            start_s=0.0,
            end_s=0.5,
            language_code="en",
        )


class FakeTts:
    def __init__(self, frame_count: int = 3) -> None:
        self._frame_count = frame_count

    async def synthesize_stream(
        self, text: str, voice: VoiceProfile
    ) -> AsyncIterator[AudioFrame]:
        for _ in range(self._frame_count):
            yield _frame()

    def list_voices(self) -> list[VoiceProfile]:
        return [VoiceProfile(voice_id="test", display_name="Test", language_code="en-US")]


class _RawVadAdapter:
    """Adapts a `FakeVad` (single-arg `is_speech(frame)`) to the
    `RawSpeechDetector`-shaped `is_speech(frame, sample_rate)` interface
    `BargeInController` expects."""

    def __init__(self, fake_vad: FakeVad) -> None:
        self._fake_vad = fake_vad

    def is_speech(self, frame: AudioFrame, sample_rate: int) -> bool:
        return self._fake_vad.is_speech(frame)


async def _collect_until(
    event_bus: EventBus, until_type: str, timeout: float = 5.0
) -> list[JarvisEvent]:
    received: list[JarvisEvent] = []

    async def collect() -> None:
        async for event in event_bus.subscribe():
            received.append(event)
            if event.type == until_type:
                return

    await asyncio.wait_for(collect(), timeout=timeout)
    return received


def _build_engine(
    *,
    orchestrator: Orchestrator,
    event_bus: EventBus,
    wake_word_frames: list[AudioFrame],
    listening_frames: list[AudioFrame],
    barge_in_frames: list[AudioFrame] | None,
    final_transcript: str = "hello jarvis",
    barge_in_enabled: bool = True,
) -> VoiceEngine:
    microphone = FakeMicrophone([wake_word_frames, listening_frames, barge_in_frames or []])
    speaker = FakeSpeaker()
    # -1: the last frame in `listening_frames` is the trailing silence
    # frame that closes the segment — see module docstring.
    vad = FakeVad(speech_frame_count=max(len(listening_frames) - 1, 0))
    pipeline = AudioStreamingPipeline(microphone, vad)  # type: ignore[arg-type]
    wake_word = FakeWakeWord(detect_on_frame_index=len(wake_word_frames))
    stt = FakeStt(final_transcript)
    tts = FakeTts()

    barge_in_controller = None
    if barge_in_enabled:
        raw_vad = FakeVad(speech_frame_count=len(barge_in_frames or []))
        barge_in_controller = BargeInController(
            speaker,  # type: ignore[arg-type]
            _RawVadAdapter(raw_vad),  # type: ignore[arg-type]
        )

    return VoiceEngine(
        audio_config=AudioConfig(),
        microphone=microphone,  # type: ignore[arg-type]
        speaker=speaker,  # type: ignore[arg-type]
        pipeline=pipeline,
        wake_word=wake_word,
        stt=stt,
        tts=tts,
        default_voice=VoiceProfile(voice_id="test", display_name="Test", language_code="en-US"),
        orchestrator=orchestrator,
        safety_gate=_permissive_safety_gate(),
        event_bus=event_bus,
        barge_in_controller=barge_in_controller,
        barge_in_enabled=barge_in_enabled,
    )


async def test_voice_engine_full_cycle_without_barge_in(
    orchestrator: Orchestrator, event_bus: EventBus
) -> None:
    engine = _build_engine(
        orchestrator=orchestrator,
        event_bus=event_bus,
        wake_word_frames=[_frame() for _ in range(3)],
        listening_frames=[_frame() for _ in range(5)] + [_frame()],
        barge_in_frames=None,
        barge_in_enabled=False,
    )

    collector = asyncio.create_task(_collect_until(event_bus, "voice.finished"))
    await asyncio.sleep(0)

    await engine.start()
    events = await collector
    await engine.stop()

    event_types = [e.type for e in events]
    assert "voice.wake" in event_types
    assert "voice.listening" in event_types
    assert "voice.final" in event_types
    assert "voice.thinking" in event_types
    assert "voice.speaking" in event_types
    assert event_types[-1] == "voice.finished"

    final_events = [e for e in events if e.type == "voice.final"]
    assert final_events[0].payload.transcript == "hello jarvis"


async def test_voice_engine_barge_in_interrupts_speaking_and_returns_to_listening(
    orchestrator: Orchestrator, event_bus: EventBus
) -> None:
    engine = _build_engine(
        orchestrator=orchestrator,
        event_bus=event_bus,
        wake_word_frames=[_frame() for _ in range(2)],
        listening_frames=[_frame() for _ in range(3)] + [_frame()],
        barge_in_frames=[_frame() for _ in range(2)],  # FakeVad reports speech immediately
        barge_in_enabled=True,
    )

    collector = asyncio.create_task(_collect_until(event_bus, "voice.interrupted"))
    await asyncio.sleep(0)

    await engine.start()
    events = await collector

    interrupted_events = [e for e in events if e.type == "voice.interrupted"]
    assert len(interrupted_events) == 1
    assert interrupted_events[0].payload.reason == "barge_in"
    assert interrupted_events[0].payload.latency_ms is not None

    await asyncio.sleep(0)  # let _speak_phase's post-interrupt state settle
    assert engine.state == VoiceState.LISTENING

    await engine.stop()


async def test_voice_engine_start_denied_without_microphone_permission(
    orchestrator: Orchestrator, event_bus: EventBus
) -> None:
    engine = _build_engine(
        orchestrator=orchestrator,
        event_bus=event_bus,
        wake_word_frames=[],
        listening_frames=[],
        barge_in_frames=None,
        barge_in_enabled=False,
    )
    engine._safety_gate = SafetyGate(SafetyPolicy.production_default())  # noqa: SLF001 -
    # deliberate whitebox override to exercise the permission-denied path.

    collector = asyncio.create_task(_collect_until(event_bus, "voice.error"))
    await asyncio.sleep(0)

    await engine.start()
    events = await collector

    assert events[-1].type == "voice.error"
    assert engine.state == VoiceState.IDLE
