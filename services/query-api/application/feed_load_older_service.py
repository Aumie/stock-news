from __future__ import annotations

from datetime import datetime
from typing import Protocol

from domain.feed import FeedItem


class FeedQueriesProtocol(Protocol):
    def recent_for_symbols(
        self, symbols: list[str], limit: int = 50, before: datetime | None = None, before_id: str | None = None
    ) -> list[FeedItem]: ...


class BackfillQueueProtocol(Protocol):
    def enqueue_symbols_backfill(self, symbols: list[str]) -> None: ...


class FeedLoadOlderService:
    """Combines "page older news" and "backfill further back" into one
    action (user request): try Postgres first (cheap), and only reach for
    Finnhub if paging is genuinely exhausted.

    The backfill itself runs as a background Celery task, not inline —
    Finnhub's company-news endpoint was found live to be unreliable enough
    (each chunk can take up to its full timeout, and the old synchronous
    version retried up to 6 times) that this endpoint could block for
    1-2+ minutes under real conditions. One click enqueues exactly one
    backfill window per symbol and returns immediately; if the page is
    still empty afterward, the user clicks "load older" again to check —
    mirrors clicking a button repeatedly rather than blocking the request
    on however long Finnhub takes (decision_log.md).
    """

    def __init__(self, feed_queries: FeedQueriesProtocol, backfill_queue: BackfillQueueProtocol) -> None:
        self._feed_queries = feed_queries
        self._backfill_queue = backfill_queue

    def load_older(
        self, symbols: list[str], before: datetime | None, before_id: str | None
    ) -> tuple[list[FeedItem], bool]:
        items = self._feed_queries.recent_for_symbols(symbols, before=before, before_id=before_id)
        if items:
            return items, False

        self._backfill_queue.enqueue_symbols_backfill(symbols)
        return [], True
