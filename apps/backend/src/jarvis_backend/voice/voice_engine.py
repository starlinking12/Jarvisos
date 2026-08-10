"""VoiceEngine — owns the Phase 3 voice interaction state machine end to
end. See ADR-0010 for the full architecture and ADR-0011 for the barge-in
design and `audio.microphone` permission model.

State machine (exactly one state active at a time, this class the sole
owner of transitions — mirrors `VoiceState` in `voice/types.py`):

    IDLE ──start()──▶ WAKE_LISTENING ──wake word──▶ LISTENING
      ▲                                                  │
      │                                          VAD end-of-speech
      │                                                  ▼
      │                                            TRANSCRIBING
      │                                                  │
      │                                          final transcript
      │                                                  ▼
      │                                              THINKING (Orchestrator)
      │                                                  │
      │                                           response ready
      │                                                  ▼
      └──stop()───────────────────────────────────── SPEAKING
                              │                           │
                    barge-in detected              playback finishes
                              ▼                           │
                          LISTENING ◀─────────────────────┘ (back to
                                                              WAKE_LISTENING)

**Single-consumer microphone stream, by design, not by accident:**
`self._microphone.frames()` (and `self._pipeline.segments()`, which wraps
it) must never be consumed by two concurrent loops — `RingBuffer.read()`
is destructive, so two simultaneous readers would each steal samples from
the other. This state machine's sequential structure guarantees exactly
one part of the engine ever iterates the microphone stream at a time:
wake-word listening consumes `pipeline.frames()` until a detection, then
stops; listening consumes a fresh `pipeline.segments()` call until one
segment completes, then stops; barge-in monitoring during `SPEAKING`
consumes a fresh `microphone.frames()` call exclusively for that state.
No two of these run concurrently.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime

import structlog
from jarvis_contracts import (
    EventSource,
    VoiceErrorEvent,
    VoiceErrorPayload,
    VoiceFinalEvent,
    VoiceFinalPayload,
    VoiceFinishedEvent,
    VoiceFinishedPayload,
    VoiceInterruptedEvent,
    VoiceInterruptedPayload,
    VoiceInterruptedReason,
    VoiceListeningEvent,
    VoiceListeningPayload,
    VoicePartialEvent,
    VoicePartialPayload,
    VoiceSpeakingEvent,
    VoiceSpeakingPayload,
    VoiceThinkingEvent,
    VoiceThinkingPayload,
    VoiceWakeEvent,
    VoiceWakePayload,
)

from jarvis_backend.agents.orchestrator import Orchestrator
from jarvis_backend.agents.safety_gate import PermissionScope, SafetyGate
from jarvis_backend.event_bus import EventBus

from .audio.pipeline import AudioStreamingPipeline
from .barge_in import BargeInController, race_playback_against_barge_in
from .stt.provider import SttProvider
from .tts.provider import TtsProvider
from .types import AudioConfig, AudioSink, AudioSource, VoiceProfile, VoiceState
from .wake_word.provider import WakeWordProvider

logger = structlog.get_logger("jarvis_backend.voice.engine")


class VoiceEngine:
    def __init__(
        self,
        *,
        audio_config: AudioConfig,
        microphone: AudioSource,
        speaker: AudioSink,
        pipeline: AudioStreamingPipeline,
        wake_word: WakeWordProvider,
        stt: SttProvider,
        tts: TtsProvider,
        default_voice: VoiceProfile,
        orchestrator: Orchestrator,
        safety_gate: SafetyGate,
        event_bus: EventBus,
        barge_in_controller: BargeInController | None = None,
        barge_in_enabled: bool = True,
    ) -> None:
        self._audio_config = audio_config
        self._microphone = microphone
        self._speaker = speaker
        self._pipeline = pipeline
        self._wake_word = wake_word
        self._stt = stt
        self._tts = tts
        self._default_voice = default_voice
        self._orchestrator = orchestrator
        self._safety_gate = safety_gate
        self._event_bus = event_bus
        self._barge_in_controller = barge_in_controller
        self._barge_in_enabled = barge_in_enabled and barge_in_controller is not None

        self._state = VoiceState.IDLE
        self._conversation_id = uuid.uuid4()
        self._run_task: asyncio.Task[None] | None = None
        self._running = False

    @property
    def state(self) -> VoiceState:
        return self._state

    @property
    def conversation_id(self) -> uuid.UUID:
        return self._conversation_id

    async def start(self) -> None:
        if self._running:
            return

        check = await self._safety_gate.check(
            PermissionScope.AUDIO_MICROPHONE,
            reason="Start Voice Engine wake-word listening",
            requested_by=EventSource.BACKEND,
            task_id=str(self._conversation_id),
        )
        if not check.granted:
            await self._publish_error(
                "Microphone permission denied — voice engine cannot start.",
                recoverable=False,
            )
            return

        await self._microphone.start()
        await self._speaker.start()
        self._running = True
        self._set_state(VoiceState.WAKE_LISTENING)
        self._run_task = asyncio.create_task(self._run_loop())
        logger.info("voice_engine_started")

    async def stop(self) -> None:
        self._running = False
        if self._run_task is not None:
            self._run_task.cancel()
            try:
                await self._run_task
            except asyncio.CancelledError:
                pass
            self._run_task = None
        await self._speaker.stop()
        await self._speaker.close()
        await self._microphone.stop()
        self._set_state(VoiceState.IDLE)
        logger.info("voice_engine_stopped")

    # -- state machine -------------------------------------------------

    async def _run_loop(self) -> None:
        while self._running:
            try:
                if self._state == VoiceState.WAKE_LISTENING:
                    await self._wake_listen_phase()
                elif self._state == VoiceState.LISTENING:
                    await self._listen_and_transcribe_phase()
                else:
                    # THINKING/SPEAKING/TRANSCRIBING/ERROR are driven
                    # linearly from within the phases above/below, not
                    # re-entered from the top of this loop.
                    await asyncio.sleep(0.05)

                # Every state-machine iteration must yield to the event loop.
                # A finite test/input source can exhaust while the engine
                # remains in WAKE_LISTENING; without this checkpoint,
                # _wake_listen_phase() returns immediately and the loop can
                # spin without reaching a cancellation point, making stop()
                # unable to cancel _run_task.
                await asyncio.sleep(0)
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001 - any unexpected failure
                # anywhere in the state machine must become a recoverable
                # voice.error and a return to wake-word listening, not a
                # dead voice engine.
                logger.exception("voice_engine_loop_error")
                await self._publish_error(str(error), recoverable=True)
                self._set_state(VoiceState.WAKE_LISTENING)

    async def _wake_listen_phase(self) -> None:
        self._wake_word.reset()
        async for frame in self._pipeline.frames():
            if not self._running or self._state != VoiceState.WAKE_LISTENING:
                return
            detection = self._wake_word.process(frame)
            if detection is not None:
                await self._event_bus.publish(
                    VoiceWakeEvent(
                        id=uuid.uuid4(),
                        source=EventSource.BACKEND,
                        timestamp=datetime.now(UTC),
                        payload=VoiceWakePayload(
                            wake_word=detection.wake_word, confidence=detection.confidence
                        ),
                    )
                )
                self._set_state(VoiceState.LISTENING)
                return

    async def _listen_and_transcribe_phase(self) -> None:
        await self._event_bus.publish(
            VoiceListeningEvent(
                id=uuid.uuid4(),
                source=EventSource.BACKEND,
                timestamp=datetime.now(UTC),
                payload=VoiceListeningPayload(listening=True),
            )
        )

        segment = None
        async for candidate in self._pipeline.segments():
            segment = candidate
            break  # exactly one utterance per listening phase

        await self._event_bus.publish(
            VoiceListeningEvent(
                id=uuid.uuid4(),
                source=EventSource.BACKEND,
                timestamp=datetime.now(UTC),
                payload=VoiceListeningPayload(listening=False),
            )
        )

        if segment is None:
            self._set_state(VoiceState.WAKE_LISTENING)
            return

        self._set_state(VoiceState.TRANSCRIBING)
        started_at = time.monotonic()
        final_text = ""
        language_code: str | None = None

        async for transcript in self._stt.stream_transcribe(segment):
            if not transcript.is_final:
                await self._event_bus.publish(
                    VoicePartialEvent(
                        id=uuid.uuid4(),
                        source=EventSource.BACKEND,
                        timestamp=datetime.now(UTC),
                        payload=VoicePartialPayload(transcript=transcript.text),
                    )
                )
            else:
                final_text = transcript.text
                language_code = transcript.language_code

        await self._event_bus.publish(
            VoiceFinalEvent(
                id=uuid.uuid4(),
                source=EventSource.BACKEND,
                timestamp=datetime.now(UTC),
                payload=VoiceFinalPayload(
                    transcript=final_text,
                    conversation_id=self._conversation_id,
                    language_code=language_code,
                    duration_ms=(time.monotonic() - started_at) * 1000,
                ),
            )
        )

        if not final_text.strip():
            self._set_state(VoiceState.WAKE_LISTENING)
            return

        await self._think_and_speak_phase(final_text)

    async def _think_and_speak_phase(self, transcript: str) -> None:
        self._set_state(VoiceState.THINKING)
        await self._event_bus.publish(
            VoiceThinkingEvent(
                id=uuid.uuid4(),
                source=EventSource.BACKEND,
                timestamp=datetime.now(UTC),
                payload=VoiceThinkingPayload(conversation_id=self._conversation_id, task_id=None),
            )
        )

        response_text = await self._orchestrator.handle_user_message(
            self._conversation_id, transcript
        )

        await self._speak_phase(response_text)

    async def _speak_phase(self, text: str) -> None:
        self._set_state(VoiceState.SPEAKING)
        await self._event_bus.publish(
            VoiceSpeakingEvent(
                id=uuid.uuid4(),
                source=EventSource.BACKEND,
                timestamp=datetime.now(UTC),
                payload=VoiceSpeakingPayload(text=text, voice_id=self._default_voice.voice_id),
            )
        )

        playback_task = asyncio.create_task(self._play_tts(text))

        barge_in_event = None
        if self._barge_in_enabled and self._barge_in_controller is not None:
            barge_in_task = asyncio.create_task(
                self._barge_in_controller.monitor(
                    self._microphone.frames(), self._audio_config.sample_rate
                )
            )
            barge_in_event = await race_playback_against_barge_in(playback_task, barge_in_task)
        else:
            await playback_task

        if barge_in_event is not None:
            await self._event_bus.publish(
                VoiceInterruptedEvent(
                    id=uuid.uuid4(),
                    source=EventSource.BACKEND,
                    timestamp=datetime.now(UTC),
                    payload=VoiceInterruptedPayload(
                        reason=VoiceInterruptedReason.BARGE_IN,
                        latency_ms=barge_in_event.interrupt_latency_ms,
                    ),
                )
            )
            self._set_state(VoiceState.LISTENING)
            return

        await self._speaker.wait_until_idle()
        await self._event_bus.publish(
            VoiceFinishedEvent(
                id=uuid.uuid4(),
                source=EventSource.BACKEND,
                timestamp=datetime.now(UTC),
                payload=VoiceFinishedPayload(voice_id=self._default_voice.voice_id),
            )
        )
        self._set_state(VoiceState.WAKE_LISTENING)

    async def _play_tts(self, text: str) -> None:
        async for frame in self._tts.synthesize_stream(text, self._default_voice):
            await self._speaker.play(frame)

    async def speak_now(self, text: str) -> bool:
        """Speaks `text` immediately, outside the normal wake→listen→
        respond cycle — used by the `voice.speak` tool (`voice/tools.py`)
        so domain agents can make the assistant say something proactively
        (e.g. a completion notification for a long-running task) without
        that becoming a full conversational turn.

        Only proceeds if the engine is idle-ish (`WAKE_LISTENING` or
        `IDLE`) — speaking over an active listen/transcribe/think cycle
        would corrupt that cycle's state machine. Returns False (and
        speaks nothing) if the engine is busy; callers should treat that
        as "try again later," not an error.
        """
        if self._state not in (VoiceState.WAKE_LISTENING, VoiceState.IDLE):
            logger.info("speak_now_skipped_busy", current_state=self._state.value)
            return False

        previous_state = self._state
        if previous_state == VoiceState.IDLE:
            await self._speaker.start()
        await self._speak_phase(text)
        if previous_state == VoiceState.IDLE:
            self._set_state(VoiceState.IDLE)
        return True

    # -- internals -------------------------------------------------------

    def _set_state(self, state: VoiceState) -> None:
        logger.debug("voice_engine_state_change", previous=self._state.value, next=state.value)
        self._state = state

    async def _publish_error(self, message: str, *, recoverable: bool) -> None:
        await self._event_bus.publish(
            VoiceErrorEvent(
                id=uuid.uuid4(),
                source=EventSource.BACKEND,
                timestamp=datetime.now(UTC),
                payload=VoiceErrorPayload(message=message, recoverable=recoverable),
            )
        )
