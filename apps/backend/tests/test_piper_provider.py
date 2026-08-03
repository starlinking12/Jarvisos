from __future__ import annotations

from pathlib import Path

import pytest

from jarvis_backend.voice.tts.piper_provider import (
    PiperBinaryNotFoundError,
    PiperProvider,
    PiperVoiceMapping,
)
from jarvis_backend.voice.types import VoiceProfile


def _voices() -> list[PiperVoiceMapping]:
    return [
        PiperVoiceMapping(
            voice_id="test-voice",
            display_name="Test Voice",
            language_code="en-US",
            model_path="voices/test.onnx",
        )
    ]


def test_provider_raises_clear_error_for_nonexistent_binary() -> None:
    with pytest.raises(PiperBinaryNotFoundError) as exc_info:
        PiperProvider(_voices(), binary_path="definitely-not-a-real-piper-binary-xyz")

    assert "definitely-not-a-real-piper-binary-xyz" in str(exc_info.value)
    assert "piper" in str(exc_info.value).lower()


def test_provider_resolves_an_existing_file_path_as_binary(tmp_path: Path) -> None:
    fake_binary = tmp_path / "fake-piper"
    fake_binary.write_text("#!/bin/sh\necho fake\n")
    fake_binary.chmod(0o755)

    provider = PiperProvider(_voices(), binary_path=str(fake_binary))
    assert provider is not None


def test_list_voices_returns_configured_voices(tmp_path: Path) -> None:
    fake_binary = tmp_path / "fake-piper"
    fake_binary.write_text("#!/bin/sh\n")
    fake_binary.chmod(0o755)

    provider = PiperProvider(_voices(), binary_path=str(fake_binary))
    voices = provider.list_voices()

    assert len(voices) == 1
    assert voices[0].voice_id == "test-voice"
    assert voices[0].language_code == "en-US"


async def test_synthesize_stream_raises_for_unknown_voice_id(tmp_path: Path) -> None:
    fake_binary = tmp_path / "fake-piper"
    fake_binary.write_text("#!/bin/sh\n")
    fake_binary.chmod(0o755)

    provider = PiperProvider(_voices(), binary_path=str(fake_binary))
    unknown_voice = VoiceProfile(
        voice_id="does-not-exist", display_name="Unknown", language_code="en-US"
    )

    with pytest.raises(ValueError):
        async for _ in provider.synthesize_stream("hello", unknown_voice):
            pass
