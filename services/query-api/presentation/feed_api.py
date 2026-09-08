from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from application.backfill_service import BackfillService
from application.feed_load_older_service import FeedLoadOlderService
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
    canonical_url: str | None


class SymbolBackfillResultResponse(BaseModel):
    symbol: str
    articles_fetched: int
    from_date: str
    to_date: str
    has_more: bool


class MultiSymbolBackfillResultResponse(BaseModel):
    total_articles_fetched: int
    per_symbol: list[SymbolBackfillResultResponse]


class LoadOlderRequest(BaseModel):
    before: datetime | None = None
    before_id: str | None = None


class LoadOlderResponse(BaseModel):
    items: list[FeedItemResponse]
    exhausted: bool


# Guarantees a newly-added symbol shows real recent articles on the first
# page instead of being crowded out by a noisier symbol's higher volume
# (real bug found live, decision_log_claude.md) — only applied when there's
# no pagination cursor yet.
FIRST_PAGE_PER_SYMBOL_LIMIT = 10


def build_feed_router(
    feed_queries: FeedQueries,
    watchlist_service: WatchlistService,
    secret: str,
    backfill_service: BackfillService | None = None,
) -> APIRouter:
    router = APIRouter()
    load_older_service = FeedLoadOlderService(feed_queries, backfill_service) if backfill_service is not None else None

    @router.get("/feed", response_model=list[FeedItemResponse])
    def feed(
        before: datetime | None = None,
        before_id: str | None = None,
        user_id: str = require_auth(secret=secret),
    ):
        symbols = [entry.symbol for entry in watchlist_service.list_symbols(user_id)]
        per_symbol_limit = FIRST_PAGE_PER_SYMBOL_LIMIT if before is None else None
        items = feed_queries.recent_for_symbols(
            symbols, before=before, before_id=before_id, per_symbol_limit=per_symbol_limit
        )
        return [
            FeedItemResponse(
                article_id=item.article_id,
                source=item.source,
                headline=item.headline,
                symbols=item.symbols,
                published_at=item.published_at.isoformat(),
                ingested_at=item.ingested_at.isoformat(),
                canonical_url=item.canonical_url,
            )
            for item in items
        ]

    @router.post("/feed/backfill-more", response_model=MultiSymbolBackfillResultResponse)
    def backfill_more(user_id: str = require_auth(secret=secret)):
        symbols = [entry.symbol for entry in watchlist_service.list_symbols(user_id)]
        result = backfill_service.load_more_for_symbols(symbols)
        return MultiSymbolBackfillResultResponse(
            total_articles_fetched=result.total_articles_fetched,
            per_symbol=[
                SymbolBackfillResultResponse(
                    symbol=r.symbol,
                    articles_fetched=r.result.articles_fetched,
                    from_date=r.result.from_date.isoformat(),
                    to_date=r.result.to_date.isoformat(),
                    has_more=r.result.has_more,
                )
                for r in result.per_symbol
            ],
        )

    @router.post("/feed/load-older", response_model=LoadOlderResponse)
    def load_older(request: LoadOlderRequest, user_id: str = require_auth(secret=secret)):
        symbols = [entry.symbol for entry in watchlist_service.list_symbols(user_id)]
        items, exhausted = load_older_service.load_older(symbols, before=request.before, before_id=request.before_id)
        return LoadOlderResponse(
            items=[
                FeedItemResponse(
                    article_id=item.article_id,
                    source=item.source,
                    headline=item.headline,
                    symbols=item.symbols,
                    published_at=item.published_at.isoformat(),
                    ingested_at=item.ingested_at.isoformat(),
                    canonical_url=item.canonical_url,
                )
                for item in items
            ],
            exhausted=exhausted,
        )

    return router
