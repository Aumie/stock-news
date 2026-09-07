from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from application.watchlist_service import WatchlistService
from infrastructure.stats_queries import StatsQueries
from presentation.auth_dependency import require_auth


class OverviewResponse(BaseModel):
    articles_ingested_today: int
    tickers_tracked: int


class RollingVolumePointResponse(BaseModel):
    date: str
    articles_today: int
    rolling_7day_avg: float


class IngestionLagResponse(BaseModel):
    avg_lag_seconds: float
    p50_lag_seconds: float
    p95_lag_seconds: float


class PriceDeltaResponse(BaseModel):
    date: str
    price_close: float
    price_change_pct: float | None


class SymbolStatsResponse(BaseModel):
    rolling_volume: list[RollingVolumePointResponse]
    ingestion_lag: IngestionLagResponse
    price_deltas: list[PriceDeltaResponse]


class StatsResponse(BaseModel):
    overview: OverviewResponse
    by_symbol: dict[str, SymbolStatsResponse]


def build_stats_router(stats_queries: StatsQueries, watchlist_service: WatchlistService, secret: str) -> APIRouter:
    router = APIRouter()

    @router.get("/stats", response_model=StatsResponse)
    def stats(user_id: str = require_auth(secret=secret)):
        symbols = [entry.symbol for entry in watchlist_service.list_symbols(user_id)]
        overview = stats_queries.overview_stats(symbols)

        by_symbol = {}
        for symbol in symbols:
            lag = stats_queries.ingestion_lag_stats(symbol)
            by_symbol[symbol] = SymbolStatsResponse(
                rolling_volume=[
                    RollingVolumePointResponse(
                        date=p.date.isoformat(), articles_today=p.articles_today, rolling_7day_avg=p.rolling_7day_avg
                    )
                    for p in stats_queries.rolling_article_volume(symbol)
                ],
                ingestion_lag=IngestionLagResponse(
                    avg_lag_seconds=lag.avg_lag_seconds,
                    p50_lag_seconds=lag.p50_lag_seconds,
                    p95_lag_seconds=lag.p95_lag_seconds,
                ),
                price_deltas=[
                    PriceDeltaResponse(date=d.date.isoformat(), price_close=d.price_close, price_change_pct=d.price_change_pct)
                    for d in stats_queries.price_deltas(symbol)
                ],
            )

        return StatsResponse(
            overview=OverviewResponse(
                articles_ingested_today=overview.articles_ingested_today,
                tickers_tracked=overview.tickers_tracked,
            ),
            by_symbol=by_symbol,
        )

    return router
