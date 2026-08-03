"""Audio device manager — enumerates and selects PortAudio devices via
`sounddevice`. `sounddevice` is a lazy import (see module docstring in
`voice/config.py` for the project's stance on optional native audio
dependencies): importing this module never fails even when `sounddevice`
isn't installed; only instantiating `AudioDeviceManager` and calling its
methods does, with a clear error pointing at the `[voice]` extras group.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType

import structlog

logger = structlog.get_logger("jarvis_backend.voice.audio.device_manager")


class AudioBackendUnavailableError(RuntimeError):
    def __init__(self, missing_package: str) -> None:
        super().__init__(
            f"'{missing_package}' is required for audio device access but is not "
            f"installed. Install it with: pip install 'jarvis-backend[voice]'"
        )


@dataclass(slots=True, frozen=True)
class AudioDeviceInfo:
    index: int
    name: str
    max_input_channels: int
    max_output_channels: int
    default_sample_rate: float
    is_default_input: bool
    is_default_output: bool


class AudioDeviceManager:
    """Thin, testable wrapper around `sounddevice`'s device query API.
    Every other voice component that needs a device index goes through
    this class rather than calling `sounddevice` directly, keeping the
    audio backend itself swappable (e.g. a future ALSA-direct or WASAPI-
    exclusive backend on a platform where PortAudio's abstraction isn't
    granular enough) without touching `MicrophoneManager`/`SpeakerManager`
    call sites.
    """

    def __init__(self) -> None:
        self._sd: ModuleType = self._import_sounddevice()

    @staticmethod
    def _import_sounddevice() -> ModuleType:
        try:
            import sounddevice as sd  # type: ignore[import-untyped]
        except ImportError as error:
            raise AudioBackendUnavailableError("sounddevice") from error
        return sd

    def list_devices(self) -> list[AudioDeviceInfo]:
        raw_devices = self._sd.query_devices()
        default_input, default_output = self._sd.default.device
        devices: list[AudioDeviceInfo] = []
        for index, device in enumerate(raw_devices):
            devices.append(
                AudioDeviceInfo(
                    index=index,
                    name=device["name"],
                    max_input_channels=device["max_input_channels"],
                    max_output_channels=device["max_output_channels"],
                    default_sample_rate=device["default_samplerate"],
                    is_default_input=(index == default_input),
                    is_default_output=(index == default_output),
                )
            )
        return devices

    def default_input_device(self) -> AudioDeviceInfo:
        for device in self.list_devices():
            if device.is_default_input:
                return device
        raise RuntimeError("No default input device reported by the audio backend")

    def default_output_device(self) -> AudioDeviceInfo:
        for device in self.list_devices():
            if device.is_default_output:
                return device
        raise RuntimeError("No default output device reported by the audio backend")

    def find_input_device(self, name_substring: str) -> AudioDeviceInfo | None:
        needle = name_substring.lower()
        for device in self.list_devices():
            if device.max_input_channels > 0 and needle in device.name.lower():
                return device
        return None

    def find_output_device(self, name_substring: str) -> AudioDeviceInfo | None:
        needle = name_substring.lower()
        for device in self.list_devices():
            if device.max_output_channels > 0 and needle in device.name.lower():
                return device
        return None
