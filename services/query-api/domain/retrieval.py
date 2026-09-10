from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RetrievedChunk:
    article_id: str
    chunk_text: str
    source: str
    headline: str
    score: float
    published_at: datetime
    canonical_url: str | None = None
