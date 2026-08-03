"""Audio ring buffer.

Real audio I/O callbacks (via `sounddevice`/PortAudio) run on a dedicated
OS thread outside asyncio's event loop, and that callback thread must
never block — a blocked audio callback means dropped/glitched audio at
the hardware level, audible to the user. `RingBuffer` is the fixed-size,
overwrite-oldest-on-overflow buffer the callback thread writes into
without ever waiting on a lock held by slower consumers; `MicrophoneManager`
drains it into an asyncio-friendly stream from a separate coroutine.

This is a genuine ring buffer (fixed-capacity circular array over a numpy
buffer), not a wrapped `queue.Queue` — a `Queue` would need unbounded
growth or blocking puts to avoid data loss, neither of which is
acceptable on a real-time audio thread.
"""

from __future__ import annotations

import threading

import numpy as np

from ..types import AudioSamples


class RingBuffer:
    """Fixed-capacity circular buffer for float32 mono audio samples.

    Thread-safety: `write()` is called from the audio callback thread;
    `read()` is called from an asyncio coroutine (typically via
    `loop.run_in_executor` if reading blocks, though this implementation's
    `read()` never blocks — it returns whatever is available, possibly
    zero samples). A single `threading.Lock` protects the shared index
    state; critical sections are O(1) index arithmetic plus a numpy copy,
    kept intentionally short to minimize contention with the real-time
    callback thread.
    """

    def __init__(self, capacity_samples: int) -> None:
        if capacity_samples <= 0:
            raise ValueError("capacity_samples must be positive")
        self._capacity = capacity_samples
        self._buffer: AudioSamples = np.zeros(capacity_samples, dtype=np.float32)
        self._write_pos = 0
        self._available = 0
        self._overflow_count = 0
        self._lock = threading.Lock()

    def write(self, samples: AudioSamples) -> None:
        """Writes `samples` into the buffer, overwriting the oldest data
        if the buffer is full. Never blocks, never raises for a full
        buffer — audio callbacks cannot tolerate either."""
        n = len(samples)
        if n == 0:
            return

        with self._lock:
            if n >= self._capacity:
                # Larger than the whole buffer — keep only the most recent
                # `capacity` samples.
                self._buffer[:] = samples[-self._capacity :]
                self._write_pos = 0
                self._available = self._capacity
                self._overflow_count += 1
                return

            end = self._write_pos + n
            if end <= self._capacity:
                self._buffer[self._write_pos : end] = samples
            else:
                first_part = self._capacity - self._write_pos
                self._buffer[self._write_pos :] = samples[:first_part]
                self._buffer[: end - self._capacity] = samples[first_part:]

            self._write_pos = end % self._capacity
            if self._available + n > self._capacity:
                self._overflow_count += 1
            self._available = min(self._available + n, self._capacity)

    def read(self, max_samples: int) -> AudioSamples:
        """Reads up to `max_samples` of the oldest available data,
        consuming it. Returns fewer samples (or zero) if less is
        available — callers loop/poll rather than block."""
        with self._lock:
            n = min(max_samples, self._available)
            if n == 0:
                return np.zeros(0, dtype=np.float32)

            read_start = (self._write_pos - self._available) % self._capacity
            end = read_start + n
            if end <= self._capacity:
                result = self._buffer[read_start:end].copy()
            else:
                first_part = self._capacity - read_start
                result = np.concatenate(
                    [self._buffer[read_start:], self._buffer[: end - self._capacity]]
                )

            self._available -= n
            return result

    @property
    def available_samples(self) -> int:
        with self._lock:
            return self._available

    @property
    def overflow_count(self) -> int:
        """Number of write() calls that caused data loss — a health
        signal `AudioStreamingPipeline` can surface if the consumer side
        is falling behind real-time capture."""
        with self._lock:
            return self._overflow_count

    def clear(self) -> None:
        with self._lock:
            self._available = 0
            self._write_pos = 0
