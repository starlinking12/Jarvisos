from __future__ import annotations

import numpy as np

from jarvis_backend.voice.types import AudioConfig, AudioFrame
from jarvis_backend.voice.vad.audio_processing import (
    AudioProcessingChain,
    NullEchoCanceller,
    NullNoiseSuppressor,
    SoftwareAgc,
)


def _make_frame(samples: np.ndarray) -> AudioFrame:
    return AudioFrame(samples=samples, config=AudioConfig(), timestamp_s=0.0)


def test_agc_amplifies_quiet_signal_toward_target() -> None:
    agc = SoftwareAgc(target_rms=0.2, attack_coefficient=1.0, release_coefficient=1.0)
    quiet_signal = np.full(320, 0.01, dtype=np.float32)

    result = agc.process(quiet_signal)

    assert np.abs(result).mean() > np.abs(quiet_signal).mean()


def test_agc_attenuates_loud_signal_toward_target() -> None:
    agc = SoftwareAgc(target_rms=0.1, attack_coefficient=1.0, release_coefficient=1.0)
    loud_signal = np.full(320, 0.9, dtype=np.float32)

    result = agc.process(loud_signal)

    assert np.abs(result).mean() < np.abs(loud_signal).mean()


def test_agc_never_exceeds_clipping_bounds() -> None:
    agc = SoftwareAgc(target_rms=0.5, max_gain=10.0)
    signal = np.full(320, 0.9, dtype=np.float32)

    result = agc.process(signal)

    assert np.all(result <= 1.0)
    assert np.all(result >= -1.0)


def test_agc_holds_gain_steady_on_silence() -> None:
    agc = SoftwareAgc()
    initial_gain = agc.current_gain
    silence = np.zeros(320, dtype=np.float32)

    agc.process(silence)

    assert agc.current_gain == initial_gain


def test_agc_empty_input_returns_empty_output() -> None:
    agc = SoftwareAgc()
    result = agc.process(np.zeros(0, dtype=np.float32))
    assert len(result) == 0


def test_agc_gain_is_bounded_by_min_and_max() -> None:
    agc = SoftwareAgc(target_rms=0.9, min_gain=0.5, max_gain=2.0, attack_coefficient=1.0)
    very_quiet = np.full(320, 0.001, dtype=np.float32)

    agc.process(very_quiet)

    assert agc.current_gain <= 2.0


def test_null_noise_suppressor_passes_through_unchanged() -> None:
    suppressor = NullNoiseSuppressor()
    samples = np.array([0.1, -0.2, 0.3], dtype=np.float32)

    result = suppressor.process(samples)

    np.testing.assert_array_equal(result, samples)


def test_null_echo_canceller_passes_through_unchanged() -> None:
    canceller = NullEchoCanceller()
    samples = np.array([0.1, -0.2, 0.3], dtype=np.float32)

    result = canceller.process(samples, reference=None)

    np.testing.assert_array_equal(result, samples)


def test_processing_chain_composes_all_stages() -> None:
    chain = AudioProcessingChain()
    frame = _make_frame(np.full(320, 0.01, dtype=np.float32))

    result = chain.process(frame)

    assert result.config == frame.config
    assert result.timestamp_s == frame.timestamp_s
    assert len(result.samples) == len(frame.samples)


def test_processing_chain_uses_injected_stages() -> None:
    class _DoublingSuppressor:
        def process(self, samples: np.ndarray) -> np.ndarray:
            return np.clip(samples * 2, -1.0, 1.0).astype(np.float32)

    chain = AudioProcessingChain(
        agc=SoftwareAgc(target_rms=1.0, attack_coefficient=0.0, release_coefficient=0.0),
        noise_suppressor=_DoublingSuppressor(),
    )
    frame = _make_frame(np.full(320, 0.1, dtype=np.float32))

    result = chain.process(frame)

    # AGC with zero attack/release coefficients holds gain at its initial
    # value (1.0), so only the injected doubling suppressor should affect
    # the output relative to the input.
    np.testing.assert_allclose(result.samples, frame.samples * 2, atol=1e-5)
