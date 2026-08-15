"""Whisper.cpp provider — wraps whisper.cpp's CLI binary via subprocess."""

from __future__ import annotations

import asyncio
import re
import shutil
import tempfile
import wave
from collections.abc import AsyncIterator
from pathlib import Path

import numpy as np
import structlog

from ..audio.pipeline import SpeechSegment
from ..types import TranscriptSegment

logger = structlog.get_logger("jarvis_backend.voice.stt.whisper_cpp")

_TIMESTAMP_LINE = re.compile(
    r"\[(?P<start>\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(?P<end>\d{2}:\d{2}:\d{2}\.\d{3})\]\s*(?P<text>.*)"
)
_DETECTED_LANGUAGE = re.compile(r"auto-detected language:\s*(\w+)", re.IGNORECASE)


class WhisperCppBinaryNotFoundError(RuntimeError):
    def __init__(self, binary_path: str) -> None:
        super().__init__(
            f"whisper.cpp binary not found at '{binary_path}'. Build whisper.cpp "
            f"(https://github.com/ggerganov/whisper.cpp) and set "
            f"JARVIS_VOICE_WHISPER_BINARY_PATH, or place the binary on PATH."
        )


def _parse_timestamp(value: str) -> float:
    hours, minutes, seconds = value.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


class WhisperCppProvider:
    """Implements `SttProvider` structurally."""

    def __init__(
        self,
        *,
        binary_path: str = "whisper-cli",
        model_path: str = "models/ggml-base.en.bin",
        language: str = "auto",
        extra_args: tuple[str, ...] = (),
    ) -> None:
        resolved = shutil.which(binary_path) or (
            binary_path if Path(binary_path).is_file() else None
        )
        if resolved is None:
            raise WhisperCppBinaryNotFoundError(binary_path)
        self._binary_path = resolved
        self._model_path = model_path
        self._language = language
        self._extra_args = extra_args

    async def stream_transcribe(self, segment: SpeechSegment) -> AsyncIterator[TranscriptSegment]:
        with tempfile.TemporaryDirectory(prefix="jarvis-whisper-") as tmp_dir:
            wav_path = Path(tmp_dir) / "utterance.wav"
            self._write_wav(wav_path, segment)

            args = [
                self._binary_path,
                "-m",
                self._model_path,
                "-f",
                str(wav_path),
                "-l",
                self._language,
                "-ml",
                "1",
                "-nt",
                *self._extra_args,
            ]

            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            assert process.stdout is not None and process.stderr is not None

            stderr_task = asyncio.create_task(process.stderr.read(), name="whisper-stderr")
            try:
                words: list[str] = []
                last_end_s = segment.start_s
                detected_language: str | None = None

                async for raw_line in process.stdout:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    match = _TIMESTAMP_LINE.match(line)
                    if not match:
                        continue

                    word = match.group("text").strip()
                    if not word:
                        continue

                    start_s = segment.start_s + _parse_timestamp(match.group("start"))
                    end_s = segment.start_s + _parse_timestamp(match.group("end"))
                    last_end_s = end_s
                    words.append(word)

                    yield TranscriptSegment(
                        text=" ".join(words),
                        is_final=False,
                        confidence=None,
                        start_s=start_s,
                        end_s=end_s,
                    )

                stderr_bytes = await stderr_task
                stderr_text = stderr_bytes.decode("utf-8", errors="replace")
                language_match = _DETECTED_LANGUAGE.search(stderr_text)
                if language_match:
                    detected_language = language_match.group(1)

                return_code = await process.wait()
                if return_code != 0:
                    logger.warning(
                        "whisper_cpp_nonzero_exit",
                        return_code=return_code,
                        stderr=stderr_text[:500],
                    )

                yield TranscriptSegment(
                    text=" ".join(words),
                    is_final=True,
                    confidence=None,
                    start_s=segment.start_s,
                    end_s=last_end_s,
                    language_code=detected_language,
                )
            finally:
                if process.returncode is None:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=1.0)
                    except TimeoutError:
                        process.kill()
                        await process.wait()

                if not stderr_task.done():
                    stderr_task.cancel()
                await asyncio.gather(stderr_task, return_exceptions=True)

    @staticmethod
    def _write_wav(path: Path, segment: SpeechSegment) -> None:
        pcm16 = (np.clip(segment.samples, -1.0, 1.0) * 32767).astype(np.int16)
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(segment.config.sample_rate)
            wav_file.writeframes(pcm16.tobytes())
