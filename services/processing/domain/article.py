from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Article:
    source: str
    headline: str
    published_at: datetime
    content: str
    canonical_url: str | None = None
    id: str | None = None
    ingested_at: datetime | None = None


@dataclass(frozen=True)
class ArticleSymbol:
    article_id: str
    symbol: str
