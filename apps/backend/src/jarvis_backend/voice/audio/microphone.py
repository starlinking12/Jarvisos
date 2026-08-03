"""Microphone manager — real-time audio capture.

`sounddevice.InputStream` invokes its callback on a dedicated PortAudio
thread. That callback does the minimum possible work (a `RingBuffer.write`
call, which is lock-protected but O(1) plus a numpy copy — see
`ring_buffer.py`'s docstring for why this specific data structure exists)
and returns immediately, never touching asyncio. `frames()` is the asyncio
side: a coroutine that polls the ring buffer at a cadence matched to
`AudioConfig.frame_duration_ms` and yields fixed-size `AudioFrame`s to the
rest of the pipeline (VAD, wake word, STT all expect fixed frame sizes).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from types import ModuleType

import numpy as np
import structlog

from ..types import AudioConfig, AudioFrame
from .device_manager import AudioBackendUnavailableError
from .ring_buffer import RingBuffer

logger = structlog.get_logger("jarvis_backend.voice.audio.microphone")

RING_BUFFER_SECONDS = 5.0  # generous headroom — consumer should drain much faster than this fills


class MicrophoneManager:
    """Captures live microphone audio and exposes it as a stream of
    fixed-duration `AudioFrame`s. Implements the `AudioSource` protocol
    (`voice/types.py`) structurally — no inheritance required, consistent
    with `ModelProvider`'s `Protocol`-based design in `ai/types.py`.
    """

    def __init__(self, config: AudioConfig, device_index: int | None = None) -> None:
        self._config = config
        self._device_index = device_index
        self._sd: ModuleType = self._import_sounddevice()
        self._ring_buffer = RingBuffer(int(config.sample_rate * RING_BUFFER_SECONDS))
        self._stream: object | None = None
        self._running = False

    @staticmethod
    def _import_sounddevice() -> ModuleType:
        try:
            import sounddevice as sd  # type: ignore[import-untyped]
        except ImportError as error:
            raise AudioBackendUnavailableError("sounddevice") from error
        return sd

    async def start(self) -> None:
        if self._running:
            return

        def _callback(indata: np.ndarray, frames: int, time_info: object, status: object) -> None:
            if status:
                logger.warning("microphone_stream_status", status=str(status))
            # indata is (frames, channels) float32; collapse to mono by
            # averaging channels if the device captures more than one.
            mono = indata.mean(axis=1) if indata.ndim > 1 else indata
            self._ring_buffer.write(mono.astype(np.float32, copy=False))

        self._stream = self._sd.InputStream(
            samplerate=self._config.sample_rate,
            channels=self._config.channels,
            device=self._device_index,
            dtype="float32",
            blocksize=self._config.frame_samples,
            callback=_callback,
        )
        self._stream.start()  # type: ignore[attr-defined]
        self._running = True
        logger.info(
            "microphone_started",
            sample_rate=self._config.sample_rate,
            device_index=self._device_index,
        )

    async def stop(self) -> None:
        if not self._running:
            return
        if self._stream is not None:
            self._stream.stop()  # type: ignore[attr-defined]
            self._stream.close()  # type: ignore[attr-defined]
            self._stream = None
        self._running = False
        self._ring_buffer.clear()
        logger.info("microphone_stopped")

    async def frames(self) -> AsyncIterator[AudioFrame]:
        """Yields fixed-size `AudioFrame`s for as long as the microphone
        is running. Polls the ring buffer at half the frame duration so
        frames are emitted with minimal added latency without busy-waiting
        the event loop."""
        frame_size = self._config.frame_samples
        poll_interval_s = (self._config.frame_duration_ms / 1000) / 2

        while self._running:
            if self._ring_buffer.available_samples >= frame_size:
                samples = self._ring_buffer.read(frame_size)
                yield AudioFrame(
                    samples=samples, config=self._config, timestamp_s=time.monotonic()
                )
            else:
                await asyncio.sleep(poll_interval_s)

    @property
    def overflow_count(self) -> int:
        """Exposed for health monitoring — a rising count means the
        pipeline consuming `frames()` is falling behind real-time
        capture."""
        return self._ring_buffer.overflow_count

    @property
    def is_running(self) -> bool:
        return self._running
