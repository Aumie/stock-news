from datetime import datetime, timezone

import pytest

from application.watchlist_service import WatchlistService
from domain.watchlist import WatchlistEntry
from infrastructure.finnhub_lookup import InvalidSymbolError


class FakeLookup:
    def __init__(self, valid_symbols: set[str]):
        self._valid_symbols = valid_symbols

    def validate(self, symbol: str) -> None:
        if symbol.upper() not in self._valid_symbols:
            raise InvalidSymbolError(f"unrecognized symbol: {symbol}")


class FakeWatchlistRepo:
    def __init__(self):
        self.entries: dict[str, list[WatchlistEntry]] = {}

    def list_for_user(self, user_id: str) -> list[WatchlistEntry]:
        return self.entries.get(user_id, [])

    def add(self, user_id: str, symbol: str) -> WatchlistEntry:
        entry = WatchlistEntry(symbol=symbol, added_at=datetime(2026, 9, 20, tzinfo=timezone.utc))
        self.entries.setdefault(user_id, []).append(entry)
        return entry

    def remove(self, user_id: str, symbol: str) -> None:
        self.entries[user_id] = [e for e in self.entries.get(user_id, []) if e.symbol != symbol]


def test_add_symbol_validates_against_finnhub_first():
    service = WatchlistService(repo=FakeWatchlistRepo(), lookup=FakeLookup({"AAPL"}))

    with pytest.raises(InvalidSymbolError):
        service.add_symbol("user-1", "NOTASYMBOL")


def test_add_symbol_persists_when_valid():
    repo = FakeWatchlistRepo()
    service = WatchlistService(repo=repo, lookup=FakeLookup({"AAPL"}))

    entry = service.add_symbol("user-1", "aapl")

    assert entry.symbol == "AAPL"  # normalized to uppercase
    assert repo.list_for_user("user-1") == [entry]


def test_list_symbols_scoped_to_user():
    repo = FakeWatchlistRepo()
    service = WatchlistService(repo=repo, lookup=FakeLookup({"AAPL", "MSFT"}))
    service.add_symbol("user-1", "AAPL")
    service.add_symbol("user-2", "MSFT")

    assert [e.symbol for e in service.list_symbols("user-1")] == ["AAPL"]
    assert [e.symbol for e in service.list_symbols("user-2")] == ["MSFT"]


def test_remove_symbol_is_idempotent():
    repo = FakeWatchlistRepo()
    service = WatchlistService(repo=repo, lookup=FakeLookup({"AAPL"}))
    service.add_symbol("user-1", "AAPL")

    service.remove_symbol("user-1", "AAPL")
    service.remove_symbol("user-1", "AAPL")  # does not raise

    assert service.list_symbols("user-1") == []


class FakeBackfillService:
    def __init__(self):
        self.backfilled_symbols: list[str] = []

    def backfill_on_add(self, symbol: str) -> None:
        self.backfilled_symbols.append(symbol)


def test_add_symbol_triggers_backfill_when_backfill_service_given():
    backfill_service = FakeBackfillService()
    service = WatchlistService(repo=FakeWatchlistRepo(), lookup=FakeLookup({"AAPL"}), backfill_service=backfill_service)

    service.add_symbol("user-1", "AAPL")

    assert backfill_service.backfilled_symbols == ["AAPL"]


def test_add_symbol_does_not_backfill_on_invalid_symbol():
    backfill_service = FakeBackfillService()
    service = WatchlistService(repo=FakeWatchlistRepo(), lookup=FakeLookup({"AAPL"}), backfill_service=backfill_service)

    with pytest.raises(InvalidSymbolError):
        service.add_symbol("user-1", "NOTASYMBOL")

    assert backfill_service.backfilled_symbols == []


def test_add_symbol_works_without_a_backfill_service():
    service = WatchlistService(repo=FakeWatchlistRepo(), lookup=FakeLookup({"AAPL"}))

    entry = service.add_symbol("user-1", "AAPL")

    assert entry.symbol == "AAPL"


class FakeJobTrigger:
    def __init__(self):
        self.triggered_symbols: list[str] = []

    def trigger_for_symbol(self, symbol: str) -> None:
        self.triggered_symbols.append(symbol)


def test_add_symbol_triggers_daily_batch_job_when_job_trigger_given():
    job_trigger = FakeJobTrigger()
    service = WatchlistService(repo=FakeWatchlistRepo(), lookup=FakeLookup({"AAPL"}), job_trigger=job_trigger)

    service.add_symbol("user-1", "AAPL")

    assert job_trigger.triggered_symbols == ["AAPL"]


def test_add_symbol_does_not_trigger_job_on_invalid_symbol():
    job_trigger = FakeJobTrigger()
    service = WatchlistService(repo=FakeWatchlistRepo(), lookup=FakeLookup({"AAPL"}), job_trigger=job_trigger)

    with pytest.raises(InvalidSymbolError):
        service.add_symbol("user-1", "NOTASYMBOL")

    assert job_trigger.triggered_symbols == []


def test_add_symbol_works_without_a_job_trigger():
    service = WatchlistService(repo=FakeWatchlistRepo(), lookup=FakeLookup({"AAPL"}))

    entry = service.add_symbol("user-1", "AAPL")

    assert entry.symbol == "AAPL"
