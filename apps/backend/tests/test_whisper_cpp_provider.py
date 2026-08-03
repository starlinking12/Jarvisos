from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import pytest

from jarvis_backend.voice.audio.pipeline import SpeechSegment
from jarvis_backend.voice.stt.whisper_cpp_provider import (
    WhisperCppBinaryNotFoundError,
    WhisperCppProvider,
    _parse_timestamp,
)
from jarvis_backend.voice.types import AudioConfig


def test_provider_raises_clear_error_for_nonexistent_binary() -> None:
    with pytest.raises(WhisperCppBinaryNotFoundError) as exc_info:
        WhisperCppProvider(binary_path="definitely-not-a-real-whisper-binary-xyz")

    assert "definitely-not-a-real-whisper-binary-xyz" in str(exc_info.value)
    assert "whisper.cpp" in str(exc_info.value)


def test_provider_resolves_an_existing_file_path_as_binary(tmp_path: Path) -> None:
    fake_binary = tmp_path / "fake-whisper"
    fake_binary.write_text("#!/bin/sh\necho fake\n")
    fake_binary.chmod(0o755)

    # Should not raise — the path exists as a file, regardless of whether
    # it's actually a working whisper.cpp binary (that's only discovered
    # when it's actually invoked).
    provider = WhisperCppProvider(binary_path=str(fake_binary))
    assert provider is not None


def test_parse_timestamp_converts_whisper_format_to_seconds() -> None:
    assert _parse_timestamp("00:00:01.500") == pytest.approx(1.5)
    assert _parse_timestamp("00:01:00.000") == pytest.approx(60.0)
    assert _parse_timestamp("01:00:00.000") == pytest.approx(3600.0)


def test_write_wav_produces_a_valid_wav_file(tmp_path: Path) -> None:
    segment = SpeechSegment(
        samples=np.zeros(1600, dtype=np.float32),
        config=AudioConfig(sample_rate=16_000),
        start_s=0.0,
        end_s=0.1,
    )
    wav_path = tmp_path / "test.wav"

    WhisperCppProvider._write_wav(wav_path, segment)

    with wave.open(str(wav_path), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 16_000
        assert wav_file.getnframes() == 1600
