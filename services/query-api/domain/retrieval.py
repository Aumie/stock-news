from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievedChunk:
    article_id: str
    chunk_text: str
    source: str
    headline: str
    score: float
