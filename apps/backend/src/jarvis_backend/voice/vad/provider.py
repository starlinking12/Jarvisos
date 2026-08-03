"""VAD provider protocol.

Structural typing, same pattern as `ModelProvider` (`ai/types.py`) and
`ToolProvider`-shaped components throughout this project — a VAD
implementation satisfies this by shape, no inheritance required, so
swapping WebRTC VAD for a future neural VAD (e.g. Silero) is a
`voice/config.py` change, never a call-site change.
"""

from __future__ import annotations

from typing import Protocol

from ..types import AudioFrame


class VadProvider(Protocol):
    def is_speech(self, frame: AudioFrame) -> bool:
        """Returns True if `frame` contains speech. Implementations may
        apply their own internal hangover/debounce smoothing (e.g. WebRTC
        VAD's aggressiveness mode) so a single frame of silence inside an
        utterance doesn't fragment it — see `WebRtcVadProvider`."""
        ...
