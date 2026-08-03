"""Piper provider — wraps the `piper` CLI binary via subprocess, streaming
raw PCM audio to stdout as it's synthesized (`piper --output-raw`), so
`VoiceEngine` can begin playback before the full utterance finishes
synthesizing — the same "don't buffer the whole thing first" principle as
`WhisperCppProvider`'s streaming reads, applied to output instead of input.

**Emotion/speaking-style abstraction:** Piper is a single-speaker (or
multi-speaker, but not emotion-controllable) neural TTS engine — it has no
emotion or speaking-style parameter. `VoiceProfile.speaking_style` is
accepted here (satisfying the `TtsProvider` protocol) but has no effect on
Piper's output beyond `speaking_rate`, which Piper *does* support natively
via `--length-scale` (a real, functioning knob — faster/slower speech, not
a no-op). This is the documented, correct behavior for Piper specifically,
not a gap: a future emotion-capable neural TTS provider (Phase 5+) reads
`speaking_style`/`pitch_semitones` for real, and every caller —
`VoiceEngine`, domain agents constructing a `VoiceProfile` — needs zero
changes when that provider replaces or joins Piper in `voice/config.py`'s
routing.
"""

from __future__ import annotations

import asyncio
import shutil
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import structlog

from ..types import AudioConfig, AudioFrame, VoiceProfile

logger = structlog.get_logger("jarvis_backend.voice.tts.piper")

PIPER_OUTPUT_SAMPLE_RATE = 22_050  # Piper's standard model output rate;
# resampled to the pipeline's AudioConfig at the SpeakerManager boundary if
# they differ.
BYTES_PER_SAMPLE = 2  # Piper emits 16-bit PCM


class PiperBinaryNotFoundError(RuntimeError):
    def __init__(self, binary_path: str) -> None:
        super().__init__(
            f"Piper binary not found at '{binary_path}'. Install it "
            f"(pip install piper-tts, or download a release binary from "
            f"https://github.com/rhasspy/piper) and set "
            f"JARVIS_VOICE_PIPER_BINARY_PATH, or place it on PATH."
        )


@dataclass(slots=True, frozen=True)
class PiperVoiceMapping:
    """Maps a `VoiceProfile.voice_id` to the on-disk Piper model files that
    voice actually uses. One `.onnx` model file per voice, per Piper's
    packaging convention."""

    voice_id: str
    display_name: str
    language_code: str
    model_path: str  # e.g. "voices/en_US-lessac-medium.onnx"


class PiperProvider:
    """Implements `TtsProvider` (`tts/provider.py`) structurally."""

    def __init__(
        self,
        voices: list[PiperVoiceMapping],
        *,
        binary_path: str = "piper",
        output_config: AudioConfig | None = None,
    ) -> None:
        resolved = shutil.which(binary_path) or (
            binary_path if Path(binary_path).is_file() else None
        )
        if resolved is None:
            raise PiperBinaryNotFoundError(binary_path)
        self._binary_path = resolved
        self._voices = {mapping.voice_id: mapping for mapping in voices}
        self._output_config = output_config or AudioConfig(sample_rate=PIPER_OUTPUT_SAMPLE_RATE)

    def list_voices(self) -> list[VoiceProfile]:
        return [
            VoiceProfile(
                voice_id=mapping.voice_id,
                display_name=mapping.display_name,
                language_code=mapping.language_code,
            )
            for mapping in self._voices.values()
        ]

    async def synthesize_stream(
        self, text: str, voice: VoiceProfile
    ) -> AsyncIterator[AudioFrame]:
        mapping = self._voices.get(voice.voice_id)
        if mapping is None:
            raise ValueError(
                f"Unknown Piper voice_id '{voice.voice_id}'. Known voices: "
                f"{list(self._voices.keys())}"
            )

        length_scale = 1.0 / max(voice.speaking_rate, 0.1)  # Piper: smaller = faster

        args = [
            self._binary_path,
            "--model",
            mapping.model_path,
            "--output-raw",
            "--length-scale",
            str(length_scale),
        ]

        started_at = time.monotonic()
        process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert process.stdin is not None and process.stdout is not None

        process.stdin.write(text.encode("utf-8") + b"\n")
        await process.stdin.drain()
        process.stdin.close()

        frame_bytes = self._output_config.frame_samples * BYTES_PER_SAMPLE
        first_frame_yielded = False

        while True:
            chunk = await process.stdout.read(frame_bytes)
            if not chunk:
                break

            samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
            if not first_frame_yielded:
                logger.debug(
                    "piper_first_audio_chunk",
                    latency_ms=(time.monotonic() - started_at) * 1000,
                )
                first_frame_yielded = True

            yield AudioFrame(
                samples=samples, config=self._output_config, timestamp_s=time.monotonic()
            )

        return_code = await process.wait()
        if return_code != 0:
            stderr = await process.stderr.read() if process.stderr else b""
            logger.warning(
                "piper_nonzero_exit",
                return_code=return_code,
                stderr=stderr.decode("utf-8", errors="replace")[:500],
            )
