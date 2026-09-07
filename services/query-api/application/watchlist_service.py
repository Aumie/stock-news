from __future__ import annotations

from typing import Protocol

from domain.watchlist import WatchlistEntry


class WatchlistRepository(Protocol):
    def list_for_user(self, user_id: str) -> list[WatchlistEntry]: ...
    def add(self, user_id: str, symbol: str) -> WatchlistEntry: ...
    def remove(self, user_id: str, symbol: str) -> None: ...


class SymbolLookup(Protocol):
    def validate(self, symbol: str) -> None: ...


class WatchlistService:
    def __init__(self, repo: WatchlistRepository, lookup: SymbolLookup) -> None:
        self._repo = repo
        self._lookup = lookup

    def list_symbols(self, user_id: str) -> list[WatchlistEntry]:
        return self._repo.list_for_user(user_id)

    def add_symbol(self, user_id: str, symbol: str) -> WatchlistEntry:
        symbol = symbol.strip().upper()
        # Raises InvalidSymbolError on rejection — let it propagate, the
        # caller (presentation layer) maps it to a 422 (§4.1, api-spec.md).
        self._lookup.validate(symbol)
        return self._repo.add(user_id, symbol)

    def remove_symbol(self, user_id: str, symbol: str) -> None:
        self._repo.remove(user_id, symbol.strip().upper())
