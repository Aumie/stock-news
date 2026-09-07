from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class RollingVolumePoint:
    symbol: str
    date: date
    articles_today: int
    rolling_7day_avg: float


@dataclass(frozen=True)
class IngestionLagStats:
    symbol: str
    avg_lag_seconds: float
    p50_lag_seconds: float
    p95_lag_seconds: float


@dataclass(frozen=True)
class PriceDelta:
    symbol: str
    date: date
    price_close: float
    price_change_pct: float | None
