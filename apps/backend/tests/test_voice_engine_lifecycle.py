from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from jarvis_backend.agents.safety_gate import PermissionDecisionKind, PermissionScope
from jarvis_backend.agents.safety_gate import SafetyGate, SafetyPolicy
from jarvis_backend.event_bus import EventBus
from jarvis_backend.voice.audio.pipeline import AudioStreamingPipeline
from jarvis_backend.voice.types import AudioConfig, VoiceProfile, VoiceState
from jarvis_backend.voice.voice_engine import VoiceEngine


class _EmptyMicrophone:
    def frames(self) -> AsyncIterator[object]:
        return self._empty()

    async def _empty(self) -> AsyncIterator[object]:
        if False:
            yield object()

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None


class _NoopSpeaker:
    async def start(self) -> None:
        return None

    async def play(self, frame: object) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def wait_until_idle(self) -> None:
        return None

    async def close(self) -> None:
        return None


class _NoopWakeWord:
    def reset(self) -> None:
        return None

    def process(self, frame: object) -> None:
        return None


class _UnusedStt:
    async def stream_transcribe(self, segment: object) -> AsyncIterator[object]:
        if False:
            yield object()


class _UnusedTts:
    async def synthesize_stream(
        self, text: str, voice: VoiceProfile
    ) -> AsyncIterator[object]:
        if False:
            yield object()


class _UnusedOrchestrator:
    async def handle_user_message(self, conversation_id: object, text: str) -> str:
        return "unused"


def _permissive_safety_gate() -> SafetyGate:
    return SafetyGate(
        SafetyPolicy(
            default=PermissionDecisionKind.DENY,
            overrides={PermissionScope.AUDIO_MICROPHONE: PermissionDecisionKind.ALLOW},
        )
    )


async def test_voice_engine_stop_remains_responsive_when_wake_stream_exhausts() -> None:
    microphone = _EmptyMicrophone()
    speaker = _NoopSpeaker()
    engine = VoiceEngine(
        audio_config=AudioConfig(),
        microphone=microphone,  # type: ignore[arg-type]
        speaker=speaker,  # type: ignore[arg-type]
        pipeline=AudioStreamingPipeline(microphone, object()),  # type: ignore[arg-type]
        wake_word=_NoopWakeWord(),  # type: ignore[arg-type]
        stt=_UnusedStt(),  # type: ignore[arg-type]
        tts=_UnusedTts(),  # type: ignore[arg-type]
        default_voice=VoiceProfile(voice_id="test", display_name="Test", language_code="en-US"),
        orchestrator=_UnusedOrchestrator(),  # type: ignore[arg-type]
        safety_gate=_permissive_safety_gate(),
        event_bus=EventBus(),
        barge_in_enabled=False,
    )

    await engine.start()
    assert engine.state == VoiceState.WAKE_LISTENING

    # Give the run loop a chance to observe the exhausted source before
    # requiring stop() to cancel it. Without a cooperative checkpoint in
    # VoiceEngine._run_loop(), this call can deadlock indefinitely.
    await asyncio.sleep(0)
    await asyncio.wait_for(engine.stop(), timeout=1.0)

    assert engine.state == VoiceState.IDLE
    assert engine._run_task is None  # noqa: SLF001 - lifecycle regression assertion
