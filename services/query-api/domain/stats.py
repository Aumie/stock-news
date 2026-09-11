from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class RollingVolumePoint:
    symbol: str
    date: date
    articles_today: int
    rolling_avg_7d: float
    rolling_avg_30d: float


@dataclass(frozen=True)
class PriceDelta:
    symbol: str
    date: date
    price_close: float
    price_change_pct: float | None


@dataclass(frozen=True)
class OverviewStats:
    articles_ingested_today: int
    tickers_tracked: int


@dataclass(frozen=True)
class BusiestSymbolDay:
    symbol: str
    date: date
    article_count: int


@dataclass(frozen=True)
class ArticleListing:
    headline: str
    source: str
    published_at: datetime
    canonical_url: str | None
