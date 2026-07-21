from __future__ import annotations
from dataclasses import dataclass, field
from ..store.models import Segment


@dataclass
class TranscriptResult:
    source: str
    lang: str | None
    full_text: str
    segments: list[Segment] = field(default_factory=list)
