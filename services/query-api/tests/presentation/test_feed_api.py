from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from application.watchlist_service import WatchlistService
from domain.feed import FeedItem
from domain.watchlist import WatchlistEntry
from presentation.feed_api import build_feed_router

SECRET = "test-secret-at-least-32-bytes-long!"


class FakeWatchlistRepo:
    def __init__(self, entries: dict[str, list[str]]):
        self._entries = entries

    def list_for_user(self, user_id: str) -> list[WatchlistEntry]:
        return [
            WatchlistEntry(symbol=s, added_at=datetime(2026, 9, 20, tzinfo=timezone.utc))
            for s in self._entries.get(user_id, [])
        ]

    def add(self, user_id, symbol):
        raise NotImplementedError

    def remove(self, user_id, symbol):
        raise NotImplementedError


class FakeFeedQueries:
    def __init__(self):
        self.last_symbols = None
        self.last_before = None
        self.last_before_id = None
        self.last_per_symbol_limit = None

    def recent_for_symbols(self, symbols, limit=50, before=None, before_id=None, per_symbol_limit=None):
        self.last_symbols = symbols
        self.last_before = before
        self.last_before_id = before_id
        self.last_per_symbol_limit = per_symbol_limit
        return [
            FeedItem(
                article_id="a1",
                source="finnhub",
                headline="h",
                symbols=symbols,
                published_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
                ingested_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
                canonical_url="https://example.com/a1",
            )
        ]


def _make_token(sub="user-1"):
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": sub, "iat": now, "exp": now + timedelta(hours=24)}, SECRET, algorithm="HS256")


@pytest.fixture
def feed_queries():
    return FakeFeedQueries()


@pytest.fixture
def client(feed_queries):
    watchlist_service = WatchlistService(repo=FakeWatchlistRepo({"user-1": ["AAPL"]}), lookup=None)
    app = FastAPI()
    app.include_router(build_feed_router(feed_queries, watchlist_service, secret=SECRET))
    return TestClient(app)


def test_feed_scoped_to_callers_watchlist(client, feed_queries):
    response = client.get("/feed", headers={"Authorization": f"Bearer {_make_token('user-1')}"})

    assert response.status_code == 200
    assert feed_queries.last_symbols == ["AAPL"]
    assert response.json()[0]["headline"] == "h"


def test_feed_requires_auth(client):
    response = client.get("/feed")

    assert response.status_code == 401


def test_feed_passes_before_cursor_through_to_query(client, feed_queries):
    response = client.get(
        "/feed",
        params={"before": "2026-09-01T00:00:00+00:00", "before_id": "abc-123"},
        headers={"Authorization": f"Bearer {_make_token('user-1')}"},
    )

    assert response.status_code == 200
    assert feed_queries.last_before is not None
    assert feed_queries.last_before_id == "abc-123"


def test_feed_without_before_cursor_passes_none(client, feed_queries):
    response = client.get("/feed", headers={"Authorization": f"Bearer {_make_token('user-1')}"})

    assert response.status_code == 200
    assert feed_queries.last_before is None
    assert feed_queries.last_before_id is None


def test_feed_first_page_requests_per_symbol_quota(client, feed_queries):
    # Real bug found live: a noisy symbol crowded a newly-added, quieter
    # symbol out of the feed entirely. The very first page (no cursor) must
    # ask FeedQueries to guarantee a per-symbol quota, not a flat top-N.
    response = client.get("/feed", headers={"Authorization": f"Bearer {_make_token('user-1')}"})

    assert response.status_code == 200
    assert feed_queries.last_per_symbol_limit is not None


def test_feed_paged_request_does_not_request_per_symbol_quota(client, feed_queries):
    # Per-symbol quota is only meaningful on the first page — a genuine
    # per-symbol cursor for paged requests is a larger redesign, deferred
    # until needed beyond the first page (decision_log_claude.md).
    response = client.get(
        "/feed",
        params={"before": "2026-09-01T00:00:00+00:00", "before_id": "abc-123"},
        headers={"Authorization": f"Bearer {_make_token('user-1')}"},
    )

    assert response.status_code == 200
    assert feed_queries.last_per_symbol_limit is None


class FakeBackfillService:
    def __init__(self, result):
        self._result = result
        self.load_more_for_symbols_calls = None

    def load_more_for_symbols(self, symbols):
        self.load_more_for_symbols_calls = symbols
        return self._result


@pytest.fixture
def backfill_service():
    from datetime import date

    from domain.backfill import BackfillResult, MultiSymbolBackfillResult, SymbolBackfillResult

    return FakeBackfillService(
        MultiSymbolBackfillResult(
            per_symbol=[
                SymbolBackfillResult(
                    symbol="AAPL",
                    result=BackfillResult(articles_fetched=12, from_date=date(2026, 8, 23), to_date=date(2026, 9, 6), has_more=True),
                )
            ]
        )
    )


@pytest.fixture
def client_with_backfill(feed_queries, backfill_service):
    watchlist_service = WatchlistService(repo=FakeWatchlistRepo({"user-1": ["AAPL"]}), lookup=None)
    app = FastAPI()
    app.include_router(build_feed_router(feed_queries, watchlist_service, secret=SECRET, backfill_service=backfill_service))
    return TestClient(app)


def test_feed_backfill_more_calls_service_with_callers_watchlist(client_with_backfill, backfill_service):
    response = client_with_backfill.post("/feed/backfill-more", headers={"Authorization": f"Bearer {_make_token('user-1')}"})

    assert response.status_code == 200
    assert backfill_service.load_more_for_symbols_calls == ["AAPL"]
    body = response.json()
    assert body["total_articles_fetched"] == 12
    assert body["per_symbol"][0]["symbol"] == "AAPL"


def test_feed_backfill_more_requires_auth(client_with_backfill):
    response = client_with_backfill.post("/feed/backfill-more")

    assert response.status_code == 401


def test_feed_load_older_returns_items_and_exhausted_flag(client_with_backfill):
    response = client_with_backfill.post(
        "/feed/load-older",
        json={"before": "2026-09-01T00:00:00+00:00", "before_id": "abc-123"},
        headers={"Authorization": f"Bearer {_make_token('user-1')}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["headline"] == "h"
    assert body["exhausted"] is False


def test_feed_load_older_without_cursor_for_first_page(client_with_backfill):
    response = client_with_backfill.post(
        "/feed/load-older", json={}, headers={"Authorization": f"Bearer {_make_token('user-1')}"}
    )

    assert response.status_code == 200


def test_feed_load_older_requires_auth(client_with_backfill):
    response = client_with_backfill.post("/feed/load-older", json={})

    assert response.status_code == 401
