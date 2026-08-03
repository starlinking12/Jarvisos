"""Speaker manager — streaming audio playback.

Playback uses `sounddevice.OutputStream` in callback mode, pulling from an
internal queue of PCM chunks fed by `play()`. The critical property this
design provides is `stop()`'s latency: it clears the pending-chunk queue
and flags the current chunk as abandoned, so PortAudio's callback stops
emitting audio within one callback period (typically a few milliseconds)
rather than waiting for the current chunk to finish — this is what makes
barge-in's sub-150ms interrupt target achievable (see ADR-0011).
"""

from __future__ import annotations

import asyncio
import time
from types import ModuleType

import numpy as np
import structlog

from ..types import AudioConfig, AudioFrame
from .device_manager import AudioBackendUnavailableError

logger = structlog.get_logger("jarvis_backend.voice.audio.speaker")


class SpeakerManager:
    """Implements the `AudioSink` protocol (`voice/types.py`) structurally.
    Playback chunks are queued via `play()` and consumed by PortAudio's
    output callback; `stop()` is the barge-in interrupt path."""

    def __init__(self, config: AudioConfig, device_index: int | None = None) -> None:
        self._config = config
        self._device_index = device_index
        self._sd: ModuleType = self._import_sounddevice()
        self._stream: object | None = None
        self._pending: list[np.ndarray] = []
        self._current_chunk: np.ndarray | None = None
        self._current_offset = 0
        self._stop_flag = False
        self._playback_finished = asyncio.Event()
        self._playback_finished.set()  # nothing playing initially

    @staticmethod
    def _import_sounddevice() -> ModuleType:
        try:
            import sounddevice as sd  # type: ignore[import-untyped]
        except ImportError as error:
            raise AudioBackendUnavailableError("sounddevice") from error
        return sd

    async def start(self) -> None:
        if self._stream is not None:
            return

        def _callback(outdata: np.ndarray, frames: int, time_info: object, status: object) -> None:
            if status:
                logger.warning("speaker_stream_status", status=str(status))

            filled = 0
            while filled < frames:
                if self._stop_flag:
                    outdata[filled:] = 0
                    self._pending.clear()
                    self._current_chunk = None
                    return

                if self._current_chunk is None:
                    if not self._pending:
                        outdata[filled:] = 0
                        return
                    self._current_chunk = self._pending.pop(0)
                    self._current_offset = 0

                remaining_in_chunk = len(self._current_chunk) - self._current_offset
                take = min(remaining_in_chunk, frames - filled)
                outdata[filled : filled + take, 0] = self._current_chunk[
                    self._current_offset : self._current_offset + take
                ]
                self._current_offset += take
                filled += take

                if self._current_offset >= len(self._current_chunk):
                    self._current_chunk = None

        self._stream = self._sd.OutputStream(
            samplerate=self._config.sample_rate,
            channels=1,
            device=self._device_index,
            dtype="float32",
            blocksize=self._config.frame_samples,
            callback=_callback,
        )
        self._stream.start()  # type: ignore[attr-defined]
        logger.info("speaker_started", device_index=self._device_index)

    async def play(self, frame: AudioFrame) -> None:
        """Queues one chunk of audio for playback. Does not block until
        playback completes — call `wait_until_idle()` for that."""
        self._stop_flag = False
        self._playback_finished.clear()
        self._pending.append(np.asarray(frame.samples, dtype=np.float32))

    async def stop(self) -> None:
        """Immediately halts playback and discards all queued/in-progress
        audio — the barge-in interrupt path. Sets `_stop_flag`, read by
        the callback on its very next invocation (bounded by one
        `blocksize`'s worth of audio at the configured sample rate, e.g.
        20ms at 16kHz — comfortably inside the 150ms barge-in budget)."""
        started_at = time.monotonic()
        self._stop_flag = True
        self._pending.clear()
        self._playback_finished.set()
        logger.info(
            "speaker_stopped", stop_latency_estimate_ms=(time.monotonic() - started_at) * 1000
        )

    async def wait_until_idle(self) -> None:
        """Awaits until all queued audio has finished playing (or `stop()`
        was called). Used by `VoiceEngine` to know when TTS playback of a
        full response has completed, to publish `voice.finished`."""
        while self._pending or self._current_chunk is not None:
            await asyncio.sleep(0.01)
        self._playback_finished.set()

    async def close(self) -> None:
        if self._stream is not None:
            self._stream.stop()  # type: ignore[attr-defined]
            self._stream.close()  # type: ignore[attr-defined]
            self._stream = None
