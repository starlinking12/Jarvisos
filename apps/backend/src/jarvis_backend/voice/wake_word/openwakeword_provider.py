"""openWakeWord provider — wraps the `openwakeword` PyPI package, a
streaming, numpy-based wake-word detection library with pretrained models
for common phrases and support for custom-trained models.

False-positive mitigation (per the Phase 3 mandate) is two-layered:
1. **Consecutive-frame requirement** — a single high-scoring frame does
   not fire a detection; `consecutive_frames_required` frames in a row
   must exceed the sensitivity threshold. Wake-word false positives are
   usually single-frame score spikes from unrelated audio; requiring
   consecutive frames filters most of them without materially increasing
   detection latency (each frame is ~80ms of audio at openWakeWord's
   native frame size).
2. **Refractory period** — after firing, further detections are
   suppressed for `refractory_period_s`, preventing one spoken wake word
   from firing repeatedly as its score stays elevated across the frames
   spanning the utterance.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import structlog

from ..types import AudioFrame, WakeWordDetection
from .provider import WakeWordConfig

logger = structlog.get_logger("jarvis_backend.voice.wake_word.openwakeword")


class OpenWakeWordUnavailableError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "'openwakeword' is required for wake-word detection but is not "
            "installed. Install it with: pip install 'jarvis-backend[voice]'"
        )


class OpenWakeWordProvider:
    """Implements `WakeWordProvider` (`wake_word/provider.py`) structurally.

    openWakeWord's native frame size is 80ms (1280 samples at 16kHz) —
    larger than this project's standard 20ms `AudioConfig` frame. Frames
    are internally buffered and only submitted to the model once a full
    80ms window has accumulated; `AudioFrame`s that don't yet complete a
    window return `None` from `process()` immediately.
    """

    NATIVE_FRAME_SAMPLES = 1280  # 80ms at 16kHz — openWakeWord's fixed input size

    def __init__(self, config: WakeWordConfig) -> None:
        self._config = config
        self._model: Any = self._build_model(config)
        self._threshold = self._sensitivity_to_threshold(config.sensitivity)
        self._consecutive_hits: dict[str, int] = {}
        self._last_fired_at: dict[str, float] = {}
        self._sample_buffer = np.zeros(0, dtype=np.float32)

    @staticmethod
    def _build_model(config: WakeWordConfig) -> Any:
        try:
            from openwakeword.model import Model  # type: ignore[import-untyped]
        except ImportError as error:
            raise OpenWakeWordUnavailableError() from error

        model_paths = list(config.extra_model_paths) or None
        # When `model_paths` is None, openWakeWord loads its bundled
        # pretrained models and filters by `wakeword_models` names below;
        # custom-trained `.onnx`/`.tflite` models are passed via
        # `extra_model_paths` in `WakeWordConfig`.
        return Model(wakeword_models=model_paths or list(config.wake_words))

    @staticmethod
    def _sensitivity_to_threshold(sensitivity: float) -> float:
        # openWakeWord scores are roughly in [0, 1]; a higher sensitivity
        # setting should mean a LOWER score threshold (easier to trigger).
        # Clamp to a sane range so sensitivity=1.0 doesn't produce a
        # threshold of 0 (which would fire on nearly any audio).
        sensitivity = min(max(sensitivity, 0.0), 1.0)
        return 0.9 - (sensitivity * 0.7)  # sensitivity 0.0 -> 0.9, 1.0 -> 0.2

    def process(self, frame: AudioFrame) -> WakeWordDetection | None:
        self._sample_buffer = np.concatenate([self._sample_buffer, frame.samples])

        detection: WakeWordDetection | None = None
        while len(self._sample_buffer) >= self.NATIVE_FRAME_SAMPLES:
            window = self._sample_buffer[: self.NATIVE_FRAME_SAMPLES]
            self._sample_buffer = self._sample_buffer[self.NATIVE_FRAME_SAMPLES :]
            window_pcm16 = (np.clip(window, -1.0, 1.0) * 32767).astype(np.int16)

            scores: dict[str, float] = self._model.predict(window_pcm16)
            fired = self._evaluate_scores(scores, frame.timestamp_s)
            if fired is not None:
                detection = fired  # keep scanning remaining buffered windows,
                # but the most recent detection in this call wins if multiple
                # windows fired within one process() call.

        return detection

    def _evaluate_scores(
        self, scores: dict[str, float], timestamp_s: float
    ) -> WakeWordDetection | None:
        for word, score in scores.items():
            if word not in self._config.wake_words and self._config.extra_model_paths == ():
                continue

            if score >= self._threshold:
                self._consecutive_hits[word] = self._consecutive_hits.get(word, 0) + 1
            else:
                self._consecutive_hits[word] = 0
                continue

            if self._consecutive_hits[word] < self._config.consecutive_frames_required:
                continue

            last_fired = self._last_fired_at.get(word, 0.0)
            if timestamp_s - last_fired < self._config.refractory_period_s:
                continue

            self._last_fired_at[word] = timestamp_s
            self._consecutive_hits[word] = 0
            logger.info("wake_word_detected", word=word, confidence=score)
            return WakeWordDetection(wake_word=word, confidence=score, timestamp_s=timestamp_s)

        return None

    def reset(self) -> None:
        self._consecutive_hits.clear()
        self._sample_buffer = np.zeros(0, dtype=np.float32)
        # Deliberately NOT clearing `_last_fired_at` — the refractory
        # period should survive a reset triggered by, e.g., a completed
        # interaction resuming wake-word listening; otherwise a lingering
        # echo of the assistant's own speech could immediately re-trigger.
