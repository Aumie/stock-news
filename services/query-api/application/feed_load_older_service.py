from __future__ import annotations

from datetime import datetime
from typing import Protocol

from domain.backfill import MultiSymbolBackfillResult
from domain.feed import FeedItem


class FeedQueriesProtocol(Protocol):
    def recent_for_symbols(
        self, symbols: list[str], limit: int = 50, before: datetime | None = None, before_id: str | None = None
    ) -> list[FeedItem]: ...


class BackfillServiceProtocol(Protocol):
    def load_more_for_symbols(self, symbols: list[str]) -> MultiSymbolBackfillResult: ...


class FeedLoadOlderService:
    """Combines "page older news" and "backfill further back" into one
    action (user request): try Postgres first (cheap), and only reach for
    Finnhub if paging is genuinely exhausted — extending automatically
    through empty windows up to a bounded number of attempts, rather than
    making the user click "load more" repeatedly through stretches with no
    news. Each attempt extends by BackfillService.BACKFILL_WINDOW_DAYS.
    """

    # Caps the worst case (a symbol with sparse or no coverage) to a handful
    # of real Finnhub calls per click, not an unbounded loop back through
    # years of empty history (user's explicit choice over no cap at all).
    MAX_BACKFILL_ATTEMPTS = 6

    def __init__(self, feed_queries: FeedQueriesProtocol, backfill_service: BackfillServiceProtocol) -> None:
        self._feed_queries = feed_queries
        self._backfill_service = backfill_service

    def load_older(
        self, symbols: list[str], before: datetime | None, before_id: str | None
    ) -> tuple[list[FeedItem], bool]:
        items = self._feed_queries.recent_for_symbols(symbols, before=before, before_id=before_id)
        if items:
            return items, False

        for _ in range(self.MAX_BACKFILL_ATTEMPTS):
            result = self._backfill_service.load_more_for_symbols(symbols)
            items = self._feed_queries.recent_for_symbols(symbols, before=before, before_id=before_id)
            if items:
                return items, False
            # has_more=False on every symbol means Finnhub returned nothing
            # for that whole window across the board — no point burning
            # through the remaining attempts on windows further back that
            # are equally likely to be empty (e.g. a genuinely dead symbol).
            if all(not r.result.has_more for r in result.per_symbol):
                break

        return [], True
