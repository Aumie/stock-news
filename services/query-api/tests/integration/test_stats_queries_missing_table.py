"""Live check for a real bug found in milestone 6 verification: /stats
returned a raw 500 (psycopg.errors.UndefinedTable) when daily_symbol_features
doesn't exist yet — true for any fresh deployment before the daily-batch job
has run once. Confirms StatsQueries degrades to empty/zeroed results instead
of crashing (docs/decision_log_claude.md).

Requires `docker compose up postgres`, and that daily_symbol_features does
NOT currently exist (this test drops it first to guarantee that state, then
does not recreate it — it's not this test's table to own).
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

from infrastructure.stats_queries import StatsQueries

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/stock-news"
)


@pytest.fixture
def engine():
    engine = create_engine(DATABASE_URL)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"Postgres not reachable at {DATABASE_URL}: {exc}")
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS daily_symbol_features"))
    yield engine


def test_rolling_article_volume_is_empty_when_table_missing(engine):
    stats = StatsQueries(engine)

    assert stats.rolling_article_volume("AAPL") == []


def test_ingestion_lag_stats_is_zeroed_when_table_missing(engine):
    stats = StatsQueries(engine)

    result = stats.ingestion_lag_stats("AAPL")

    assert result.avg_lag_seconds == 0.0
    assert result.p50_lag_seconds == 0.0
    assert result.p95_lag_seconds == 0.0


def test_price_deltas_is_empty_when_table_missing(engine):
    stats = StatsQueries(engine)

    assert stats.price_deltas("AAPL") == []
