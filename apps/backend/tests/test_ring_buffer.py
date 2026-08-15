from __future__ import annotations

import numpy as np
import pytest

from jarvis_backend.voice.audio.ring_buffer import RingBuffer


def test_write_then_read_round_trip() -> None:
    buffer = RingBuffer(capacity_samples=100)
    samples = np.arange(10, dtype=np.float32)
    buffer.write(samples)
    result = buffer.read(10)
    np.testing.assert_array_equal(result, samples)


def test_read_returns_fewer_samples_than_available() -> None:
    buffer = RingBuffer(capacity_samples=100)
    buffer.write(np.arange(5, dtype=np.float32))
    result = buffer.read(100)
    assert len(result) == 5


def test_read_from_empty_buffer_returns_empty_array() -> None:
    buffer = RingBuffer(capacity_samples=100)
    result = buffer.read(10)
    assert len(result) == 0


def test_wraparound_write_and_read() -> None:
    buffer = RingBuffer(capacity_samples=10)
    buffer.write(np.arange(8, dtype=np.float32))
    buffer.read(8)
    buffer.write(np.arange(100, 106, dtype=np.float32))
    result = buffer.read(6)
    np.testing.assert_array_equal(result, np.arange(100, 106, dtype=np.float32))


def test_overflow_overwrites_oldest_data_without_raising() -> None:
    buffer = RingBuffer(capacity_samples=5)
    buffer.write(np.array([1, 2, 3, 4, 5], dtype=np.float32))
    buffer.write(np.array([6, 7], dtype=np.float32))
    result = buffer.read(5)
    np.testing.assert_array_equal(result, np.array([3, 4, 5, 6, 7], dtype=np.float32))
    assert buffer.overflow_count == 1


def test_write_larger_than_capacity_keeps_most_recent() -> None:
    buffer = RingBuffer(capacity_samples=5)
    buffer.write(np.arange(20, dtype=np.float32))
    result = buffer.read(5)
    np.testing.assert_array_equal(result, np.arange(15, 20, dtype=np.float32))


def test_clear_resets_available_samples() -> None:
    buffer = RingBuffer(capacity_samples=10)
    buffer.write(np.arange(5, dtype=np.float32))
    assert buffer.available_samples == 5
    buffer.clear()
    assert buffer.available_samples == 0
    assert len(buffer.read(10)) == 0


def test_write_empty_array_is_a_no_op() -> None:
    buffer = RingBuffer(capacity_samples=10)
    buffer.write(np.zeros(0, dtype=np.float32))
    assert buffer.available_samples == 0


def test_invalid_capacity_raises() -> None:
    with pytest.raises(ValueError):
        RingBuffer(capacity_samples=0)


def test_negative_read_size_raises() -> None:
    buffer = RingBuffer(capacity_samples=10)
    with pytest.raises(ValueError, match="max_samples"):
        buffer.read(-1)
