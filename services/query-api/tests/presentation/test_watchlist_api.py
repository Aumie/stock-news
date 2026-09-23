from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from application.watchlist_service import WatchlistService
from domain.watchlist import WatchlistEntry
from infrastructure.finnhub_lookup import InvalidSymbolError, SymbolLookupUnavailableError
from presentation.watchlist_api import build_watchlist_router

SECRET = "test-secret-at-least-32-bytes-long!"


class FakeLookup:
    def __init__(self, valid_symbols: set[str]):
        self._valid_symbols = valid_symbols

    def validate(self, symbol: str) -> None:
        if symbol.upper() not in self._valid_symbols:
            raise InvalidSymbolError(f"unrecognized symbol: {symbol}")


class FakeUnavailableLookup:
    def validate(self, symbol: str) -> None:
        raise SymbolLookupUnavailableError("Finnhub is down")


class FakeWatchlistRepo:
    def __init__(self):
        self.entries: dict[str, list[WatchlistEntry]] = {}

    def list_for_user(self, user_id: str) -> list[WatchlistEntry]:
        return self.entries.get(user_id, [])

    def add(self, user_id: str, symbol: str) -> WatchlistEntry:
        entry = WatchlistEntry(symbol=symbol, added_at=datetime(2026, 9, 20, tzinfo=timezone.utc))
        self.entries.setdefault(user_id, [e for e in self.entries.get(user_id, []) if e.symbol != symbol])
        self.entries[user_id].append(entry)
        return entry

    def remove(self, user_id: str, symbol: str) -> None:
        self.entries[user_id] = [e for e in self.entries.get(user_id, []) if e.symbol != symbol]


class FakeBackfillProgressRepo:
    def __init__(self, completed_symbols: set[str] | None = None):
        self._completed = completed_symbols or set()

    def get_earliest_backfilled(self, symbol: str):
        from datetime import date

        return date(2026, 9, 1) if symbol in self._completed else None

    def set_earliest_backfilled(self, symbol: str, earliest) -> None:
        self._completed.add(symbol)


def _make_token(sub="user-1"):
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": sub, "iat": now, "exp": now + timedelta(hours=24)}, SECRET, algorithm="HS256")


@pytest.fixture
def backfill_progress_repo():
    return FakeBackfillProgressRepo()


@pytest.fixture
def client(backfill_progress_repo):
    service = WatchlistService(repo=FakeWatchlistRepo(), lookup=FakeLookup({"AAPL", "MSFT"}))
    app = FastAPI()
    app.include_router(build_watchlist_router(service, secret=SECRET, backfill_progress_repo=backfill_progress_repo))
    return TestClient(app)


def _auth_headers(sub="user-1"):
    return {"X-App-Authorization": f"Bearer {_make_token(sub)}"}


def test_get_watchlist_starts_empty(client):
    response = client.get("/watchlist", headers=_auth_headers())

    assert response.status_code == 200
    assert response.json() == []


def test_post_valid_symbol_returns_201(client):
    response = client.post("/watchlist", json={"symbol": "AAPL"}, headers=_auth_headers())

    assert response.status_code == 201
    assert response.json()["symbol"] == "AAPL"


def test_get_watchlist_marks_symbol_as_backfill_pending_before_completion(client):
    # A newly-added symbol has no symbol_backfill_progress row yet — the
    # news/price backfill runs in a background Celery task now, not inline
    # (decision_log.md), so GET /watchlist needs to say "still pending"
    # rather than silently showing an entry indistinguishable from one
    # whose backfill already landed.
    client.post("/watchlist", json={"symbol": "AAPL"}, headers=_auth_headers())

    response = client.get("/watchlist", headers=_auth_headers())

    assert response.json()[0]["backfill_pending"] is True


def test_get_watchlist_marks_symbol_as_not_pending_once_backfill_completes(client, backfill_progress_repo):
    client.post("/watchlist", json={"symbol": "AAPL"}, headers=_auth_headers())
    backfill_progress_repo.set_earliest_backfilled("AAPL", None)

    response = client.get("/watchlist", headers=_auth_headers())

    assert response.json()[0]["backfill_pending"] is False


def test_post_invalid_symbol_returns_422(client):
    response = client.post("/watchlist", json={"symbol": "NOTASYMBOL"}, headers=_auth_headers())

    assert response.status_code == 422


def test_post_symbol_returns_503_when_finnhub_lookup_is_unavailable():
    # Real bug found live: a genuine Finnhub 503 propagated as an unhandled
    # httpx.HTTPStatusError, crashing this endpoint with a raw 500 instead
    # of a distinguishable "try again" response (decision_log.md).
    service = WatchlistService(repo=FakeWatchlistRepo(), lookup=FakeUnavailableLookup())
    app = FastAPI()
    app.include_router(build_watchlist_router(service, secret=SECRET))
    client = TestClient(app)

    response = client.post("/watchlist", json={"symbol": "AAPL"}, headers=_auth_headers())

    assert response.status_code == 503


def test_delete_symbol_returns_204(client):
    client.post("/watchlist", json={"symbol": "AAPL"}, headers=_auth_headers())

    response = client.delete("/watchlist/AAPL", headers=_auth_headers())

    assert response.status_code == 204
    assert client.get("/watchlist", headers=_auth_headers()).json() == []


def test_watchlist_is_scoped_per_user(client):
    client.post("/watchlist", json={"symbol": "AAPL"}, headers=_auth_headers("user-1"))
    client.post("/watchlist", json={"symbol": "MSFT"}, headers=_auth_headers("user-2"))

    response = client.get("/watchlist", headers=_auth_headers("user-1"))

    assert [entry["symbol"] for entry in response.json()] == ["AAPL"]


def test_no_auth_header_returns_401(client):
    response = client.get("/watchlist")

    assert response.status_code == 401
