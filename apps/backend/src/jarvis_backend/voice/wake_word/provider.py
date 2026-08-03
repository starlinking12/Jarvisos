"""Wake word provider protocol and shared config types.

Structural typing, consistent with `VadProvider`/`ModelProvider` — an
implementation satisfies `WakeWordProvider` by shape, so swapping
openWakeWord for a future alternative engine is a `voice/config.py`
change, not a call-site change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..types import AudioFrame, WakeWordDetection


@dataclass(slots=True, frozen=True)
class WakeWordConfig:
    """Configurable wake words + sensitivity, per the Phase 3 mandate.
    `sensitivity` is a single 0.0-1.0 knob mapped onto each provider's own
    native threshold representation (openWakeWord uses a raw model-score
    threshold — see `OpenWakeWordProvider._sensitivity_to_threshold`).
    """

    wake_words: tuple[str, ...] = ("jarvis",)
    sensitivity: float = 0.5  # 0.0 = least sensitive (fewest false positives,
    # more missed detections), 1.0 = most sensitive (opposite trade-off).
    # False-positive mitigation: require this many consecutive
    # above-threshold frames before firing a detection, rather than acting
    # on a single high-scoring frame — see OpenWakeWordProvider.
    consecutive_frames_required: int = 3
    # After a detection fires, ignore further detections for this long —
    # prevents a single utterance of the wake word from firing multiple
    # times as its score stays elevated across several frames.
    refractory_period_s: float = 2.0
    extra_model_paths: tuple[str, ...] = field(default_factory=tuple)


class WakeWordProvider(Protocol):
    def process(self, frame: AudioFrame) -> WakeWordDetection | None:
        """Feeds one frame to the wake-word model. Returns a
        `WakeWordDetection` if a wake word just fired (after the
        provider's own consecutive-frame/refractory-period gating —
        see `WakeWordConfig`), else `None`."""
        ...

    def reset(self) -> None:
        """Clears any internal detection-smoothing state (consecutive-frame
        counters, refractory timers) — called by `VoiceEngine` when
        transitioning states, e.g. after a full interaction completes and
        wake-word listening resumes."""
        ...
