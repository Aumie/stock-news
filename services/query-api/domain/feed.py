from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class FeedItem:
    article_id: str
    source: str
    headline: str
    symbols: list[str]
    published_at: datetime
    ingested_at: datetime
