"""Voice Engine configuration.

Follows the same pattern as `config.py`'s Phase 2 additions
(`ProviderConfig`/`RoutingConfig`): typed pydantic models, loaded from a
single JSON env var with sensible built-in defaults, so no env var needs
to be set for local development against a standard install (a local
Ollama + whisper.cpp + Piper + openWakeWord setup).

**On optional native dependencies:** `sounddevice`, `webrtcvad`, and
`openwakeword` are declared in `pyproject.toml`'s `[voice]` extras group,
not core dependencies — a JARVIS OS install that never enables voice
should not be forced to build/install native audio bindings. Every
provider module in `voice/` lazy-imports its native dependency and raises
a clear, actionable error (`AudioBackendUnavailableError`,
`WebRtcVadUnavailableError`, `OpenWakeWordUnavailableError`,
`WhisperCppBinaryNotFoundError`, `PiperBinaryNotFoundError`) only when
actually instantiated without it installed — never at import time.
"""

from __future__ import annotations

import json
from functools import lru_cache

from pydantic import BaseModel, Field

from .tts.piper_provider import PiperVoiceMapping
from .types import AudioConfig
from .wake_word.provider import WakeWordConfig


class AudioDeviceSettings(BaseModel):
    input_device_index: int | None = None  # None = system default
    output_device_index: int | None = None  # None = system default
    sample_rate: int = 16_000
    frame_duration_ms: int = 20


class VadSettings(BaseModel):
    aggressiveness: int = 2  # 0-3, WebRTC VAD's native sensitivity parameter
    hangover_frames: int = 8  # ~160ms of trailing-silence tolerance at 20ms frames


class WhisperSettings(BaseModel):
    binary_path: str = "whisper-cli"
    model_path: str = "models/ggml-base.en.bin"
    language: str = "auto"


class PiperVoiceSettingsEntry(BaseModel):
    voice_id: str
    display_name: str
    language_code: str
    model_path: str


class PiperSettings(BaseModel):
    binary_path: str = "piper"
    default_voice_id: str = "en_US-lessac-medium"
    voices: list[PiperVoiceSettingsEntry] = Field(
        default_factory=lambda: [
            PiperVoiceSettingsEntry(
                voice_id="en_US-lessac-medium",
                display_name="Lessac (US English, medium)",
                language_code="en-US",
                model_path="voices/en_US-lessac-medium.onnx",
            )
        ]
    )


class WakeWordSettings(BaseModel):
    wake_words: list[str] = Field(default_factory=lambda: ["jarvis"])
    sensitivity: float = 0.5
    consecutive_frames_required: int = 3
    refractory_period_s: float = 2.0


class VoiceSettings(BaseModel):
    """Root Voice Engine configuration. Mirrors `config.Settings`'
    JSON-env-var pattern — see `JARVIS_VOICE_SETTINGS_JSON` in
    `main.py`'s composition root."""

    enabled: bool = False  # voice engine is opt-in; requires audio.microphone
    # permission (see ADR-0011) and real audio hardware, so it defaults off
    # rather than attempting to start on every backend launch.
    devices: AudioDeviceSettings = Field(default_factory=AudioDeviceSettings)
    vad: VadSettings = Field(default_factory=VadSettings)
    wake_word: WakeWordSettings = Field(default_factory=WakeWordSettings)
    whisper: WhisperSettings = Field(default_factory=WhisperSettings)
    piper: PiperSettings = Field(default_factory=PiperSettings)
    barge_in_enabled: bool = True

    def audio_config(self) -> AudioConfig:
        return AudioConfig(
            sample_rate=self.devices.sample_rate,
            channels=1,
            frame_duration_ms=self.devices.frame_duration_ms,
        )

    def wake_word_config(self) -> WakeWordConfig:
        return WakeWordConfig(
            wake_words=tuple(self.wake_word.wake_words),
            sensitivity=self.wake_word.sensitivity,
            consecutive_frames_required=self.wake_word.consecutive_frames_required,
            refractory_period_s=self.wake_word.refractory_period_s,
        )

    def piper_voice_mappings(self) -> list[PiperVoiceMapping]:
        return [
            PiperVoiceMapping(
                voice_id=entry.voice_id,
                display_name=entry.display_name,
                language_code=entry.language_code,
                model_path=entry.model_path,
            )
            for entry in self.piper.voices
        ]


def default_voice_settings() -> VoiceSettings:
    return VoiceSettings()


@lru_cache
def get_voice_settings(raw_json: str | None = None) -> VoiceSettings:
    """Cached accessor, mirroring `config.get_settings()`. Accepts an
    optional raw JSON string (from `JARVIS_VOICE_SETTINGS_JSON`) so
    `main.py` controls exactly when/whether the env var is read, keeping
    this module import-safe and side-effect-free otherwise."""
    if not raw_json:
        return default_voice_settings()
    return VoiceSettings.model_validate(json.loads(raw_json))


__all__ = [
    "AudioDeviceSettings",
    "PiperSettings",
    "PiperVoiceSettingsEntry",
    "VadSettings",
    "VoiceSettings",
    "WakeWordSettings",
    "WhisperSettings",
    "default_voice_settings",
    "get_voice_settings",
]
