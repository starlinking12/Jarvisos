"""TTS provider protocol.

Structural typing, consistent with every other provider abstraction.
`synthesize_stream` yields `AudioFrame`s as they're generated, so
`VoiceEngine` can begin playback before the full utterance is synthesized
— critical for perceived latency on longer responses.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from ..types import AudioFrame, VoiceProfile


class TtsProvider(Protocol):
    def synthesize_stream(self, text: str, voice: VoiceProfile) -> AsyncIterator[AudioFrame]:
        """Synthesizes `text` in `voice`, yielding audio frames as they
        become available (not buffering the entire utterance first)."""
        ...

    def list_voices(self) -> list[VoiceProfile]:
        """Returns every voice this provider can currently synthesize —
        used to populate `voice/config.py`'s voice-selection setting."""
        ...
