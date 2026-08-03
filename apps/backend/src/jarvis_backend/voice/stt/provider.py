"""STT provider protocol.

Structural typing, consistent with every other provider abstraction in
this project. `stream_transcribe` yields `TranscriptSegment`s — zero or
more partials (`is_final=False`) followed by exactly one final
(`is_final=True`) — for one complete `SpeechSegment` (a VAD-delimited
utterance, see `audio/pipeline.py`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from ..audio.pipeline import SpeechSegment
from ..types import TranscriptSegment


class SttProvider(Protocol):
    def stream_transcribe(self, segment: SpeechSegment) -> AsyncIterator[TranscriptSegment]:
        """Transcribes one VAD-delimited utterance, yielding partial
        transcripts as they become available and exactly one final
        transcript (`is_final=True`) once complete."""
        ...
