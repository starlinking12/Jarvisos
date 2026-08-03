"""Shared types for the Voice Engine (Phase 3, see ADR-0010).

Every voice subsystem (audio I/O, wake word, VAD, STT, TTS) speaks this
vocabulary — `AudioFrame`, `AudioConfig`, `TranscriptSegment`,
`VoiceProfile` — exactly as `ai/types.py`'s `ChatMessage`/`ModelCapabilities`
serve the ModelRouter subsystem (ADR-0002). No provider-specific shape
leaks past its own provider module.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

try:
    import numpy as np
    from numpy.typing import NDArray

    AudioSamples = NDArray[np.float32]
except ImportError:  # pragma: no cover - numpy is a core voice dependency,
    # but importing this module for type-checking purposes (e.g. from a
    # context that never instantiates real audio I/O) should not hard-fail.
    AudioSamples = object  # type: ignore[assignment,misc]

__all__ = [
    "AudioSamples",
    "AudioConfig",
    "AudioFrame",
    "VoiceState",
    "WakeWordDetection",
    "TranscriptSegment",
    "SpeakingStyle",
    "VoiceProfile",
    "AudioSink",
    "AudioSource",
]


@dataclass(slots=True, frozen=True)
class AudioConfig:
    """The single audio format every voice subsystem agrees on. Mixed
    sample rates/channel counts between subsystems is a common source of
    subtle bugs in voice pipelines — this project standardizes on one
    config, resampling at the I/O boundary (`MicrophoneManager`/
    `SpeakerManager`) if a specific provider requires something else
    (e.g. whisper.cpp wants 16kHz mono regardless of device capture rate).
    """

    sample_rate: int = 16_000
    channels: int = 1
    frame_duration_ms: int = 20  # 20ms frames = 320 samples at 16kHz, the
    # standard WebRTC VAD frame size (WebRTC VAD only accepts 10/20/30ms).

    @property
    def frame_samples(self) -> int:
        return int(self.sample_rate * self.frame_duration_ms / 1000)


@dataclass(slots=True, frozen=True)
class AudioFrame:
    """One fixed-duration chunk of PCM audio, flowing through the entire
    capture → VAD → wake-word → STT pipeline. `samples` is float32 in
    [-1.0, 1.0] (the numpy-ecosystem convention `sounddevice`/`openwakeword`
    both expect); providers needing 16-bit PCM bytes (webrtcvad, whisper.cpp
    subprocess stdin) convert at their own boundary, not here.
    """

    samples: AudioSamples
    config: AudioConfig
    timestamp_s: float


class VoiceState(str, Enum):
    """The Voice Engine's top-level state machine. Exactly one state is
    active at a time; `VoiceEngine` is the sole owner of transitions —
    see ADR-0010's state diagram."""

    IDLE = "idle"  # voice engine not running
    WAKE_LISTENING = "wake_listening"  # always-on wake-word detection
    LISTENING = "listening"  # actively recording user speech post-wake
    TRANSCRIBING = "transcribing"  # STT finalizing after VAD end-of-speech
    THINKING = "thinking"  # Orchestrator processing the transcript
    SPEAKING = "speaking"  # TTS playback in progress
    ERROR = "error"


@dataclass(slots=True, frozen=True)
class WakeWordDetection:
    wake_word: str
    confidence: float
    timestamp_s: float


@dataclass(slots=True, frozen=True)
class TranscriptSegment:
    text: str
    is_final: bool
    confidence: float | None
    start_s: float
    end_s: float
    language_code: str | None = None


class SpeakingStyle(str, Enum):
    """Abstraction for future emotion/style-capable TTS voices (per the
    Phase 3 mandate: "Emotion and speaking-style abstraction for future
    voices"). Piper — the Phase 3 TTS provider — has no style control, so
    `PiperProvider` accepts and silently ignores this field today; a
    future neural TTS provider (Phase 5+) reads it for real. Declaring it
    now means `VoiceProfile` and every call site that constructs one never
    changes when that provider arrives — only `TtsProvider.synthesize`'s
    concrete implementation does, per "every subsystem must be
    replaceable.\""""

    NEUTRAL = "neutral"
    CALM = "calm"
    URGENT = "urgent"
    FRIENDLY = "friendly"
    SERIOUS = "serious"


@dataclass(slots=True, frozen=True)
class VoiceProfile:
    voice_id: str
    display_name: str
    language_code: str
    speaking_style: SpeakingStyle = SpeakingStyle.NEUTRAL
    speaking_rate: float = 1.0  # 1.0 = provider default
    pitch_semitones: float = 0.0  # 0.0 = provider default


class AudioSource(Protocol):
    """What `MicrophoneManager` and any future audio source (e.g. a virtual
    microphone for testing, or a network audio input) both satisfy."""

    def frames(self) -> AsyncIterator[AudioFrame]: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...


class AudioSink(Protocol):
    """What `SpeakerManager` and any future playback target satisfy. Lists
    every operation `VoiceEngine`'s state machine actually calls —
    `start`/`play`/`stop` for basic playback and barge-in, `close` for
    full teardown, `wait_until_idle` for detecting normal playback
    completion (as opposed to a barge-in interrupt) — so this protocol is
    a complete substitute for `SpeakerManager` in tests, not a partial one
    that silently requires the concrete class for anything beyond the
    basics.
    """

    async def start(self) -> None: ...

    async def play(self, frame: AudioFrame) -> None: ...

    async def stop(self) -> None: ...

    async def wait_until_idle(self) -> None: ...

    async def close(self) -> None: ...
