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

    def recent_for_symbols(self, symbols, limit=50):
        self.last_symbols = symbols
        return [
            FeedItem(
                article_id="a1",
                source="finnhub",
                headline="h",
                symbols=symbols,
                published_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
                ingested_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
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
