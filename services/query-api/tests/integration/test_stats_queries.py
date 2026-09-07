"""Real end-to-end check for milestone 5's stats-query requirement
(docs/milestone.md §5, docs/stock-news-digest-requirements.md §4.6/§4.6's
"non-trivial SQL... window functions" line): verifies the window-function
queries against a real Postgres `daily_symbol_features` table.

`daily_symbol_features` is a dbt-managed table normally produced by the
daily-batch job (services/daily-batch) — this test creates/drops its own
copy so it doesn't depend on that job having run first, matching how the
real table's shape is defined in services/daily-batch/dbt/models/daily_symbol_features.sql.

Requires a running Postgres from `docker compose up postgres`.
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text

from infrastructure.stats_queries import StatsQueries

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/stock-news"
)


@pytest.fixture(scope="module")
def engine():
    engine = create_engine(DATABASE_URL)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"Postgres not reachable at {DATABASE_URL}: {exc}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS daily_symbol_features (
                    symbol TEXT NOT NULL,
                    date DATE NOT NULL,
                    article_count INT NOT NULL,
                    avg_ingestion_lag_seconds DOUBLE PRECISION,
                    price_close DOUBLE PRECISION,
                    price_volume BIGINT,
                    price_change_pct DOUBLE PRECISION,
                    PRIMARY KEY (symbol, date)
                )
                """
            )
        )
    yield engine
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE daily_symbol_features"))


@pytest.fixture
def seeded(engine):
    rows = [
        ("TESTSYM", date(2026, 9, 14), 2, 30.0, 100.0, 1000, None),
        ("TESTSYM", date(2026, 9, 15), 1, 45.0, 102.0, 1200, 2.0),
        ("TESTSYM", date(2026, 9, 16), 5, 60.0, 101.0, 1100, -0.98),
        ("TESTSYM", date(2026, 9, 17), 0, None, 105.0, 1300, 3.96),
        ("TESTSYM", date(2026, 9, 18), 3, 15.0, 104.0, 1250, -0.95),
    ]
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM daily_symbol_features WHERE symbol = 'TESTSYM'"))
        for symbol, dt, count, lag, close, volume, change in rows:
            conn.execute(
                text(
                    """
                    INSERT INTO daily_symbol_features
                        (symbol, date, article_count, avg_ingestion_lag_seconds, price_close, price_volume, price_change_pct)
                    VALUES (:symbol, :date, :count, :lag, :close, :volume, :change)
                    """
                ),
                {"symbol": symbol, "date": dt, "count": count, "lag": lag, "close": close, "volume": volume, "change": change},
            )
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM daily_symbol_features WHERE symbol = 'TESTSYM'"))


def test_rolling_7day_article_volume(engine, seeded):
    stats = StatsQueries(engine)

    points = stats.rolling_article_volume("TESTSYM")

    assert [p.date for p in points] == [date(2026, 9, 14 + i) for i in range(5)]
    # last day's 7-day rolling avg over all 5 seeded days: (2+1+5+0+3)/5 = 2.2
    assert points[-1].rolling_7day_avg == pytest.approx(2.2)
    assert points[-1].articles_today == 3


def test_ingestion_lag_stats(engine, seeded):
    stats = StatsQueries(engine)

    result = stats.ingestion_lag_stats("TESTSYM")

    assert result.symbol == "TESTSYM"
    assert result.avg_lag_seconds == pytest.approx(37.5)  # avg of 30, 45, 60, 15 (nulls excluded)


def test_price_deltas(engine, seeded):
    stats = StatsQueries(engine)

    deltas = stats.price_deltas("TESTSYM")

    assert len(deltas) == 5
    assert deltas[0].price_change_pct is None
    assert deltas[1].price_change_pct == pytest.approx(2.0)


@pytest.fixture
def seeded_articles(engine):
    now = datetime.now(timezone.utc)
    ids = []
    for headline, symbol, published_at, ingested_at in [
        ("today AAPL 1", "AAPL", now - timedelta(hours=1), now - timedelta(hours=1)),
        ("today AAPL 2", "AAPL", now - timedelta(hours=2), now - timedelta(hours=2)),
        ("yesterday AAPL", "AAPL", now - timedelta(days=1, hours=1), now - timedelta(days=1, hours=1)),
        ("today MSFT unwatched", "MSFT", now - timedelta(hours=1), now - timedelta(hours=1)),
    ]:
        article_id = str(uuid.uuid4())
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO articles (id, source, headline, published_at, ingested_at, canonical_url, normalized_headline)
                    VALUES (CAST(:id AS uuid), 'finnhub', :headline, :published_at, :ingested_at, :url, :normalized)
                    """
                ),
                {
                    "id": article_id,
                    "headline": headline,
                    "published_at": published_at,
                    "ingested_at": ingested_at,
                    "url": f"https://example.com/{article_id}",
                    "normalized": headline.lower(),
                },
            )
            conn.execute(
                text("INSERT INTO article_symbols (article_id, symbol) VALUES (CAST(:id AS uuid), :symbol)"),
                {"id": article_id, "symbol": symbol},
            )
        ids.append(article_id)
    yield ids
    with engine.begin() as conn:
        for article_id in ids:
            conn.execute(text("DELETE FROM article_symbols WHERE article_id = CAST(:id AS uuid)"), {"id": article_id})
            conn.execute(text("DELETE FROM articles WHERE id = CAST(:id AS uuid)"), {"id": article_id})


def test_overview_stats_scoped_to_watched_symbols(engine, seeded_articles):
    stats = StatsQueries(engine)

    overview = stats.overview_stats(["AAPL"])

    assert overview.articles_ingested_today == 2  # the two today-AAPL articles, not the MSFT one or yesterday's
    assert overview.tickers_tracked == 1
