from __future__ import annotations

from typing import Protocol

from domain.watchlist import WatchlistEntry


class WatchlistRepository(Protocol):
    def list_for_user(self, user_id: str) -> list[WatchlistEntry]: ...
    def add(self, user_id: str, symbol: str) -> WatchlistEntry: ...
    def remove(self, user_id: str, symbol: str) -> None: ...


class SymbolLookup(Protocol):
    def validate(self, symbol: str) -> None: ...


class BackfillTrigger(Protocol):
    def backfill_on_add(self, symbol: str) -> object: ...


class JobTrigger(Protocol):
    def trigger_for_symbol(self, symbol: str) -> None: ...


class WatchlistService:
    def __init__(
        self,
        repo: WatchlistRepository,
        lookup: SymbolLookup,
        backfill_service: BackfillTrigger | None = None,
        job_trigger: JobTrigger | None = None,
    ) -> None:
        self._repo = repo
        self._lookup = lookup
        self._backfill_service = backfill_service
        self._job_trigger = job_trigger

    def list_symbols(self, user_id: str) -> list[WatchlistEntry]:
        return self._repo.list_for_user(user_id)

    def add_symbol(self, user_id: str, symbol: str) -> WatchlistEntry:
        symbol = symbol.strip().upper()
        # Raises InvalidSymbolError on rejection — let it propagate, the
        # caller (presentation layer) maps it to a 422 (§4.1, api-spec.md).
        self._lookup.validate(symbol)
        entry = self._repo.add(user_id, symbol)
        if self._backfill_service is not None:
            self._backfill_service.backfill_on_add(symbol)
        if self._job_trigger is not None:
            self._job_trigger.trigger_for_symbol(symbol)
        return entry

    def remove_symbol(self, user_id: str, symbol: str) -> None:
        self._repo.remove(user_id, symbol.strip().upper())
