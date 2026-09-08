from __future__ import annotations

from typing import Protocol

from domain.watchlist import WatchlistEntry


class WatchlistRepository(Protocol):
    def list_for_user(self, user_id: str) -> list[WatchlistEntry]: ...
    def add(self, user_id: str, symbol: str) -> WatchlistEntry: ...
    def remove(self, user_id: str, symbol: str) -> None: ...


class SymbolLookup(Protocol):
    def validate(self, symbol: str) -> None: ...


class BackfillQueue(Protocol):
    def enqueue_symbol_backfill(self, symbol: str) -> None: ...


class WatchlistService:
    def __init__(
        self,
        repo: WatchlistRepository,
        lookup: SymbolLookup,
        backfill_queue: BackfillQueue | None = None,
    ) -> None:
        self._repo = repo
        self._lookup = lookup
        self._backfill_queue = backfill_queue

    def list_symbols(self, user_id: str) -> list[WatchlistEntry]:
        return self._repo.list_for_user(user_id)

    def add_symbol(self, user_id: str, symbol: str) -> WatchlistEntry:
        symbol = symbol.strip().upper()
        # Raises InvalidSymbolError on rejection — let it propagate, the
        # caller (presentation layer) maps it to a 422 (§4.1, api-spec.md).
        self._lookup.validate(symbol)
        entry = self._repo.add(user_id, symbol)
        # News + price backfill run as a background Celery task, not inline —
        # the synchronous version could take 30s-2min+ under Finnhub's known
        # flakiness (decision_log.md), which made "add a symbol" feel hung
        # from the UI's perspective even when it would eventually succeed.
        # Enqueueing is expected to be near-instant regardless of how long
        # the backfill itself takes.
        if self._backfill_queue is not None:
            self._backfill_queue.enqueue_symbol_backfill(symbol)
        return entry

    def remove_symbol(self, user_id: str, symbol: str) -> None:
        self._repo.remove(user_id, symbol.strip().upper())
