from datetime import date, datetime, timedelta, timezone

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from application.watchlist_service import WatchlistService
from domain.stats import OverviewStats, PriceDelta, RollingVolumePoint
from domain.watchlist import WatchlistEntry
from presentation.stats_api import build_stats_router

SECRET = "test-secret-at-least-32-bytes-long!"

TODAY = date(2026, 9, 20)
WITHIN_7D = TODAY - timedelta(days=3)
OLDER_THAN_7D_WITHIN_30D = TODAY - timedelta(days=15)


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

    def total_ingestion(self, symbol):
        return (42, 150)  # (7d, 30d)

    def rolling_article_volume(self, symbol):
        return [
            RollingVolumePoint(
                symbol=symbol, date=OLDER_THAN_7D_WITHIN_30D, articles_today=9, rolling_avg_7d=9.0, rolling_avg_30d=9.0
            ),
            RollingVolumePoint(
                symbol=symbol, date=WITHIN_7D, articles_today=2, rolling_avg_7d=1.5, rolling_avg_30d=5.5
            ),
        ]

    def price_deltas(self, symbol):
        return [
            PriceDelta(symbol=symbol, date=OLDER_THAN_7D_WITHIN_30D, price_close=90.0, price_change_pct=None),
            PriceDelta(symbol=symbol, date=WITHIN_7D, price_close=100.0, price_change_pct=1.2),
        ]


def _make_token(sub="user-1"):
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": sub, "iat": now, "exp": now + timedelta(hours=24)}, SECRET, algorithm="HS256")


@pytest.fixture
def stats_queries():
    return FakeStatsQueries()


@pytest.fixture
def client(stats_queries):
    watchlist_service = WatchlistService(repo=FakeWatchlistRepo({"user-1": ["AAPL"]}), lookup=None)
    app = FastAPI()
    app.include_router(build_stats_router(stats_queries, watchlist_service, secret=SECRET))
    return TestClient(app)


def test_stats_returns_overview_and_per_symbol_breakdown(client):
    response = client.get("/stats", headers={"X-App-Authorization": f"Bearer {_make_token('user-1')}"})

    assert response.status_code == 200
    body = response.json()
    assert body["overview"]["articles_ingested_today"] == 3
    assert body["overview"]["tickers_tracked"] == 1
    assert body["by_symbol"]["AAPL"]["window_7d"]["total_articles"] == 42
    assert body["by_symbol"]["AAPL"]["window_30d"]["total_articles"] == 150


def test_stats_returns_both_windows_in_one_call_no_days_param_needed(client):
    response = client.get("/stats", headers={"X-App-Authorization": f"Bearer {_make_token('user-1')}"})

    assert response.status_code == 200
    body = response.json()
    assert "window_7d" in body["by_symbol"]["AAPL"]
    assert "window_30d" in body["by_symbol"]["AAPL"]


def test_stats_7d_window_excludes_points_older_than_7_days(client):
    response = client.get("/stats", headers={"X-App-Authorization": f"Bearer {_make_token('user-1')}"})

    window_7d = response.json()["by_symbol"]["AAPL"]["window_7d"]
    dates = [row["date"] for row in window_7d["rolling_volume"]]
    assert OLDER_THAN_7D_WITHIN_30D.isoformat() not in dates
    assert WITHIN_7D.isoformat() in dates
    price_dates = [row["date"] for row in window_7d["price_deltas"]]
    assert OLDER_THAN_7D_WITHIN_30D.isoformat() not in price_dates


def test_stats_30d_window_includes_points_older_than_7_days(client):
    response = client.get("/stats", headers={"X-App-Authorization": f"Bearer {_make_token('user-1')}"})

    window_30d = response.json()["by_symbol"]["AAPL"]["window_30d"]
    dates = [row["date"] for row in window_30d["rolling_volume"]]
    assert OLDER_THAN_7D_WITHIN_30D.isoformat() in dates
    assert WITHIN_7D.isoformat() in dates


def test_stats_windows_use_their_own_rolling_avg_field(client):
    response = client.get("/stats", headers={"X-App-Authorization": f"Bearer {_make_token('user-1')}"})

    body = response.json()
    window_7d_point = next(
        r for r in body["by_symbol"]["AAPL"]["window_7d"]["rolling_volume"] if r["date"] == WITHIN_7D.isoformat()
    )
    window_30d_point = next(
        r for r in body["by_symbol"]["AAPL"]["window_30d"]["rolling_volume"] if r["date"] == WITHIN_7D.isoformat()
    )
    assert window_7d_point["rolling_avg"] == 1.5
    assert window_30d_point["rolling_avg"] == 5.5


def test_stats_requires_auth(client):
    response = client.get("/stats")

    assert response.status_code == 401
