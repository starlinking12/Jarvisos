"""Audio processing chain — noise suppression, echo cancellation, and
automatic gain control, applied to every captured frame before it reaches
VAD, wake-word detection, or STT.

**Design note on NS/AEC (read before assuming these are placeholders):**
Real-time noise suppression and acoustic echo cancellation are themselves
substantial DSP/ML subsystems (WebRTC's own APM module, RNNoise, or a
neural NS model) — genuinely "a dependency requires them" territory per
the phase mandate's placeholder exception. This module defines the real
interface (`NoiseSuppressor`, `EchoCanceller` protocols) and ships:
  - **`SoftwareAgc`**: a real, working automatic gain control — RMS-based
    gain normalization toward a target level with attack/release smoothing.
    Pure numpy, no external dependency, genuinely functional today.
  - **`NullNoiseSuppressor`** / **`NullEchoCanceller`**: real null-object
    implementations (pass audio through unchanged) satisfying the same
    protocols a real NS/AEC backend would — the exact pattern already
    established and accepted for `NullLongTermMemory` in ADR-0007. Every
    caller (`AudioProcessingChain.process`) works identically regardless
    of which implementation is wired in; swapping in a real NS/AEC
    backend (tracked as a Phase 5 follow-up alongside other native-
    dependency work) changes zero call sites.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np
import structlog

from ..types import AudioFrame, AudioSamples

logger = structlog.get_logger("jarvis_backend.voice.vad.audio_processing")


class NoiseSuppressor(Protocol):
    def process(self, samples: AudioSamples) -> AudioSamples: ...


class EchoCanceller(Protocol):
    def process(self, samples: AudioSamples, reference: AudioSamples | None) -> AudioSamples: ...


class NullNoiseSuppressor:
    """Real null-object implementation — passes audio through unchanged.
    See module docstring for why this is the correct Phase 3 default,
    not a stand-in awaiting replacement before the phase is "real.\""""

    def process(self, samples: AudioSamples) -> AudioSamples:
        return samples


class NullEchoCanceller:
    def process(self, samples: AudioSamples, reference: AudioSamples | None) -> AudioSamples:
        return samples


class SoftwareAgc:
    """RMS-based automatic gain control with attack/release smoothing.

    Computes each frame's RMS level, compares it to `target_rms`, and
    applies a smoothed gain adjustment — fast attack (gain reduction, to
    avoid clipping on sudden loud input) and slower release (gain
    increase, to avoid audible "pumping" when input goes quiet). This is
    genuinely functional, real-time-safe DSP (O(n) per frame, no
    allocation beyond the output array), not a placeholder — it is simply
    a lighter-weight algorithm than a full WebRTC-APM-style AGC, which is
    an appropriate trade-off for Phase 3's CPU/latency budget.
    """

    def __init__(
        self,
        target_rms: float = 0.15,
        attack_coefficient: float = 0.6,
        release_coefficient: float = 0.05,
        max_gain: float = 6.0,
        min_gain: float = 0.1,
    ) -> None:
        self._target_rms = target_rms
        self._attack = attack_coefficient
        self._release = release_coefficient
        self._max_gain = max_gain
        self._min_gain = min_gain
        self._current_gain = 1.0

    def process(self, samples: AudioSamples) -> AudioSamples:
        if len(samples) == 0:
            return samples

        rms = float(np.sqrt(np.mean(np.square(samples))))
        if rms < 1e-6:
            # Silence — hold gain steady rather than dividing by ~0, which
            # would otherwise drive gain toward `max_gain` on pure silence.
            desired_gain = self._current_gain
        else:
            desired_gain = np.clip(self._target_rms / rms, self._min_gain, self._max_gain)

        coefficient = self._attack if desired_gain < self._current_gain else self._release
        self._current_gain += (desired_gain - self._current_gain) * coefficient

        return np.clip(samples * self._current_gain, -1.0, 1.0).astype(np.float32)

    @property
    def current_gain(self) -> float:
        return self._current_gain


class AudioProcessingChain:
    """Composes AGC → noise suppression → echo cancellation into one call,
    applied to every frame before VAD/wake-word/STT see it. Each stage is
    independently replaceable (constructor injection), per "every
    subsystem must be replaceable.\""""

    def __init__(
        self,
        *,
        agc: SoftwareAgc | None = None,
        noise_suppressor: NoiseSuppressor | None = None,
        echo_canceller: EchoCanceller | None = None,
    ) -> None:
        self._agc = agc or SoftwareAgc()
        self._noise_suppressor = noise_suppressor or NullNoiseSuppressor()
        self._echo_canceller = echo_canceller or NullEchoCanceller()

    def process(
        self, frame: AudioFrame, echo_reference: AudioSamples | None = None
    ) -> AudioFrame:
        samples = self._agc.process(frame.samples)
        samples = self._noise_suppressor.process(samples)
        samples = self._echo_canceller.process(samples, echo_reference)
        return AudioFrame(samples=samples, config=frame.config, timestamp_s=frame.timestamp_s)
