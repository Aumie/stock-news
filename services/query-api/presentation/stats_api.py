from __future__ import annotations

from datetime import date, timedelta

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
    rolling_avg: float


class PriceDeltaResponse(BaseModel):
    date: str
    price_close: float
    price_change_pct: float | None


class WindowStatsResponse(BaseModel):
    total_articles: int
    rolling_volume: list[RollingVolumePointResponse]
    price_deltas: list[PriceDeltaResponse]


class SymbolStatsResponse(BaseModel):
    window_7d: WindowStatsResponse
    window_30d: WindowStatsResponse


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
            total_7d, total_30d = stats_queries.total_ingestion(symbol)

            volume_points = stats_queries.rolling_article_volume(symbol)
            volume_7d = [p for p in volume_points if p.date >= date.today() - timedelta(days=7)]

            price_points = stats_queries.price_deltas(symbol)
            price_7d = [p for p in price_points if p.date >= date.today() - timedelta(days=7)]

            by_symbol[symbol] = SymbolStatsResponse(
                window_7d=WindowStatsResponse(
                    total_articles=total_7d,
                    rolling_volume=[
                        RollingVolumePointResponse(
                            date=p.date.isoformat(), articles_today=p.articles_today, rolling_avg=p.rolling_avg_7d
                        )
                        for p in volume_7d
                    ],
                    price_deltas=[
                        PriceDeltaResponse(date=d.date.isoformat(), price_close=d.price_close, price_change_pct=d.price_change_pct)
                        for d in price_7d
                    ],
                ),
                window_30d=WindowStatsResponse(
                    total_articles=total_30d,
                    rolling_volume=[
                        RollingVolumePointResponse(
                            date=p.date.isoformat(), articles_today=p.articles_today, rolling_avg=p.rolling_avg_30d
                        )
                        for p in volume_points
                    ],
                    price_deltas=[
                        PriceDeltaResponse(date=d.date.isoformat(), price_close=d.price_close, price_change_pct=d.price_change_pct)
                        for d in price_points
                    ],
                ),
            )

        return StatsResponse(
            overview=OverviewResponse(
                articles_ingested_today=overview.articles_ingested_today,
                tickers_tracked=overview.tickers_tracked,
            ),
            by_symbol=by_symbol,
        )

    return router
