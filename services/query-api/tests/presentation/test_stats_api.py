from datetime import date, datetime, timedelta, timezone

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from application.watchlist_service import WatchlistService
from domain.stats import IngestionLagStats, OverviewStats, PriceDelta, RollingVolumePoint
from domain.watchlist import WatchlistEntry
from presentation.stats_api import build_stats_router

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


class FakeStatsQueries:
    def overview_stats(self, symbols):
        return OverviewStats(articles_ingested_today=3, tickers_tracked=len(symbols))

    def rolling_article_volume(self, symbol):
        return [RollingVolumePoint(symbol=symbol, date=date(2026, 9, 20), articles_today=2, rolling_7day_avg=1.5)]

    def ingestion_lag_stats(self, symbol):
        return IngestionLagStats(symbol=symbol, avg_lag_seconds=30.0, p50_lag_seconds=25.0, p95_lag_seconds=60.0)

    def price_deltas(self, symbol):
        return [PriceDelta(symbol=symbol, date=date(2026, 9, 20), price_close=100.0, price_change_pct=1.2)]


def _make_token(sub="user-1"):
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": sub, "iat": now, "exp": now + timedelta(hours=24)}, SECRET, algorithm="HS256")


@pytest.fixture
def client():
    watchlist_service = WatchlistService(repo=FakeWatchlistRepo({"user-1": ["AAPL"]}), lookup=None)
    app = FastAPI()
    app.include_router(build_stats_router(FakeStatsQueries(), watchlist_service, secret=SECRET))
    return TestClient(app)


def test_stats_returns_overview_and_per_symbol_breakdown(client):
    response = client.get("/stats", headers={"Authorization": f"Bearer {_make_token('user-1')}"})

    assert response.status_code == 200
    body = response.json()
    assert body["overview"]["articles_ingested_today"] == 3
    assert body["overview"]["tickers_tracked"] == 1
    assert body["by_symbol"]["AAPL"]["rolling_volume"][0]["articles_today"] == 2
    assert body["by_symbol"]["AAPL"]["ingestion_lag"]["p95_lag_seconds"] == 60.0
    assert body["by_symbol"]["AAPL"]["price_deltas"][0]["price_change_pct"] == 1.2


def test_stats_requires_auth(client):
    response = client.get("/stats")

    assert response.status_code == 401
