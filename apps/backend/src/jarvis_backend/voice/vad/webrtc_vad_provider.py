"""WebRTC VAD provider — wraps Google's WebRTC voice activity detector
(the `webrtcvad` PyPI package, a Python binding to the same VAD used in
Chrome/WebRTC). Operates on 10/20/30ms 16-bit PCM frames at 8/16/32/48kHz
— `AudioConfig`'s defaults (16kHz, 20ms frames) are chosen specifically to
satisfy this constraint without resampling.
"""

from __future__ import annotations

from collections import deque
from typing import Any

import numpy as np
import structlog

from ..types import AudioFrame

logger = structlog.get_logger("jarvis_backend.voice.vad.webrtc")

VALID_SAMPLE_RATES = {8_000, 16_000, 32_000, 48_000}
VALID_FRAME_DURATIONS_MS = {10, 20, 30}


class WebRtcVadUnavailableError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "'webrtcvad' is required for voice activity detection but is not "
            "installed. Install it with: pip install 'jarvis-backend[voice]'"
        )


class WebRtcVadProvider:
    """Implements `VadProvider` (`vad/provider.py`) structurally.

    Applies hangover smoothing: a configurable number of consecutive
    non-speech frames must be observed before `is_speech()` reports False
    for an utterance in progress, so brief pauses mid-sentence (a person
    taking a breath) don't fragment one utterance into several
    `SpeechSegment`s. Aggressiveness mode (0-3, WebRTC VAD's own
    sensitivity parameter — higher is more aggressive about filtering
    non-speech) is configurable via `voice/config.py`'s `VadSettings`.
    """

    def __init__(
        self,
        *,
        sample_rate: int = 16_000,
        frame_duration_ms: int = 20,
        aggressiveness: int = 2,
        hangover_frames: int = 8,  # 8 * 20ms = 160ms of trailing silence tolerance
    ) -> None:
        if sample_rate not in VALID_SAMPLE_RATES:
            raise ValueError(f"WebRTC VAD requires sample_rate in {VALID_SAMPLE_RATES}")
        if frame_duration_ms not in VALID_FRAME_DURATIONS_MS:
            raise ValueError(
                f"WebRTC VAD requires frame_duration_ms in {VALID_FRAME_DURATIONS_MS}"
            )
        if not 0 <= aggressiveness <= 3:
            raise ValueError("aggressiveness must be 0-3")

        self._sample_rate = sample_rate
        self._vad: Any = self._build_vad(aggressiveness)
        self._recent_speech: deque[bool] = deque(maxlen=hangover_frames)

    @staticmethod
    def _build_vad(aggressiveness: int) -> Any:
        try:
            import webrtcvad  # type: ignore[import-untyped]
        except ImportError as error:
            raise WebRtcVadUnavailableError() from error
        return webrtcvad.Vad(aggressiveness)

    def is_speech(self, frame: AudioFrame) -> bool:
        pcm16 = self._to_pcm16_bytes(frame)
        raw_is_speech = self._vad.is_speech(pcm16, self._sample_rate)
        self._recent_speech.append(raw_is_speech)

        # Speech if this frame OR any recent frame within the hangover
        # window was speech — the hangover, not the raw per-frame result,
        # is what `AudioStreamingPipeline.segments()` actually consumes.
        return any(self._recent_speech)

    @property
    def raw_engine(self) -> Any:
        """The underlying `webrtcvad.Vad` instance, with none of this
        class's hangover smoothing applied. Exposed specifically for
        `BargeInController`/`RawSpeechDetector` (`voice/barge_in.py`),
        which deliberately need the raw per-frame signal for latency
        reasons — see that module's docstring. No other caller should
        need this; prefer `is_speech()` for anything that benefits from
        segment-continuity smoothing."""
        return self._vad

    @staticmethod
    def _to_pcm16_bytes(frame: AudioFrame) -> bytes:
        samples = np.clip(frame.samples, -1.0, 1.0)
        pcm16 = (samples * 32767).astype(np.int16)
        return pcm16.tobytes()
