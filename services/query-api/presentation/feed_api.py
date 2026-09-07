from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from application.watchlist_service import WatchlistService
from infrastructure.feed_queries import FeedQueries
from presentation.auth_dependency import require_auth


class FeedItemResponse(BaseModel):
    article_id: str
    source: str
    headline: str
    symbols: list[str]
    published_at: str
    ingested_at: str


def build_feed_router(feed_queries: FeedQueries, watchlist_service: WatchlistService, secret: str) -> APIRouter:
    router = APIRouter()

    @router.get("/feed", response_model=list[FeedItemResponse])
    def feed(user_id: str = require_auth(secret=secret)):
        symbols = [entry.symbol for entry in watchlist_service.list_symbols(user_id)]
        items = feed_queries.recent_for_symbols(symbols)
        return [
            FeedItemResponse(
                article_id=item.article_id,
                source=item.source,
                headline=item.headline,
                symbols=item.symbols,
                published_at=item.published_at.isoformat(),
                ingested_at=item.ingested_at.isoformat(),
            )
            for item in items
        ]

    return router
