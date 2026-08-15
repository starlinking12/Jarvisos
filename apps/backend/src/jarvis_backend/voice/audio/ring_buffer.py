"""Thread-safe fixed-capacity ring buffer for float32 mono audio."""

from __future__ import annotations

import threading

import numpy as np

from ..types import AudioSamples


class RingBuffer:
    """Fixed-capacity circular buffer for audio samples."""

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
        """Write samples, overwriting the oldest data on overflow."""
        n = len(samples)
        if n == 0:
            return

        with self._lock:
            if n > self._capacity:
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
        """Read and consume up to `max_samples` oldest samples."""
        if max_samples < 0:
            raise ValueError("max_samples must be non-negative")
        if max_samples == 0:
            return np.zeros(0, dtype=np.float32)

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
        with self._lock:
            return self._overflow_count

    def clear(self) -> None:
        with self._lock:
            self._available = 0
            self._write_pos = 0
