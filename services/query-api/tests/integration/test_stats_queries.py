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
    today = date.today()
    rows = [
        (today - timedelta(days=4), 2, 100.0, 1000, None),
        (today - timedelta(days=3), 1, 102.0, 1200, 2.0),
        (today - timedelta(days=2), 5, 101.0, 1100, -0.98),
        (today - timedelta(days=1), 0, 105.0, 1300, 3.96),
        (today, 3, 104.0, 1250, -0.95),
    ]
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM daily_symbol_features WHERE symbol = 'TESTSYM'"))
        for dt, count, close, volume, change in rows:
            conn.execute(
                text(
                    """
                    INSERT INTO daily_symbol_features
                        (symbol, date, article_count, price_close, price_volume, price_change_pct)
                    VALUES ('TESTSYM', :date, :count, :close, :volume, :change)
                    """
                ),
                {"date": dt, "count": count, "close": close, "volume": volume, "change": change},
            )
    yield today
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM daily_symbol_features WHERE symbol = 'TESTSYM'"))


def test_rolling_article_volume_computes_both_7d_and_30d_averages_in_one_call(engine, seeded):
    stats = StatsQueries(engine)

    points = stats.rolling_article_volume("TESTSYM")

    today = seeded
    assert [p.date for p in points] == [today - timedelta(days=4 - i) for i in range(5)]
    # last day's rolling avg over all 5 seeded days (all within both windows): (2+1+5+0+3)/5 = 2.2
    assert points[-1].rolling_avg_7d == pytest.approx(2.2)
    assert points[-1].rolling_avg_30d == pytest.approx(2.2)
    assert points[-1].articles_today == 3


def test_rolling_article_volume_7d_and_30d_genuinely_differ_with_older_data(engine, seeded):
    # Windows are ROWS BETWEEN N PRECEDING (row-count, not calendar-day-range)
    # — correct as long as daily_symbol_features has no date gaps, which
    # holds under normal operation (its date grain is a union of prices dates
    # and article-activity dates, so every day gets a row, decision_log.md).
    # Filling in the gap days here (not skipping straight to day-10) keeps
    # this test realistic instead of exercising a gap that can't occur live.
    stats = StatsQueries(engine)
    today = seeded
    with engine.begin() as conn:
        for days_ago in range(5, 10):
            conn.execute(
                text(
                    """
                    INSERT INTO daily_symbol_features (symbol, date, article_count)
                    VALUES ('TESTSYM', :date, 0)
                    """
                ),
                {"date": today - timedelta(days=days_ago)},
            )
        conn.execute(
            text(
                """
                INSERT INTO daily_symbol_features (symbol, date, article_count)
                VALUES ('TESTSYM', :date, 100)
                """
            ),
            {"date": today - timedelta(days=10)},  # the 11th row back — outside a 7-row window, inside a 30-row one
        )

    points = stats.rolling_article_volume("TESTSYM")
    last = points[-1]

    # 7-row avg only sees the last 7 rows (today back through day-6) — the day-10 row falls outside it
    assert last.rolling_avg_7d == pytest.approx(2.2 * 5 / 7)  # (2+1+5+0+3+0+0)/7
    # 30-row avg includes the day-10 row's 100, pulling the average up substantially
    assert last.rolling_avg_30d > last.rolling_avg_7d


def test_rolling_article_volume_excludes_days_outside_the_30day_fetch(engine, seeded):
    stats = StatsQueries(engine)
    today = seeded
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO daily_symbol_features (symbol, date, article_count)
                VALUES ('TESTSYM', :date, 999)
                """
            ),
            {"date": today - timedelta(days=40)},
        )

    points = stats.rolling_article_volume("TESTSYM")

    assert all(p.date >= today - timedelta(days=30) for p in points)
    assert 999 not in [p.articles_today for p in points]


def test_total_ingestion_returns_both_7d_and_30d_sums_in_one_call(engine, seeded):
    stats = StatsQueries(engine)

    total_7d, total_30d = stats.total_ingestion("TESTSYM")

    assert total_7d == 2 + 1 + 5 + 0 + 3  # all 5 seeded days fall within the last 7
    assert total_30d == 2 + 1 + 5 + 0 + 3  # same, since nothing seeded is older than 7 days here


def test_total_ingestion_7d_excludes_a_day_that_30d_includes(engine, seeded):
    stats = StatsQueries(engine)
    today = seeded
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO daily_symbol_features (symbol, date, article_count)
                VALUES ('TESTSYM', :date, 100)
                """
            ),
            {"date": today - timedelta(days=10)},  # within 30d, outside 7d
        )

    total_7d, total_30d = stats.total_ingestion("TESTSYM")

    assert total_7d == 2 + 1 + 5 + 0 + 3  # the day-10 row must not be counted here
    assert total_30d == 2 + 1 + 5 + 0 + 3 + 100  # but must be counted here


def test_total_ingestion_excludes_days_outside_the_30day_fetch(engine, seeded):
    stats = StatsQueries(engine)
    today = seeded
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO daily_symbol_features (symbol, date, article_count)
                VALUES ('TESTSYM', :date, 999)
                """
            ),
            {"date": today - timedelta(days=40)},
        )

    _, total_30d = stats.total_ingestion("TESTSYM")

    assert total_30d == 2 + 1 + 5 + 0 + 3  # the 40-day-old row must not be counted


def test_price_deltas_returns_up_to_30_days(engine, seeded):
    stats = StatsQueries(engine)

    deltas = stats.price_deltas("TESTSYM")

    assert len(deltas) == 5
    assert deltas[0].price_change_pct is None
    assert deltas[1].price_change_pct == pytest.approx(2.0)


@pytest.fixture
def seeded_articles(engine):
    # Uses made-up symbols (TESTSYM/TESTSYM2), not real tickers like AAPL —
    # a real bug found live: the live poller continuously ingests real AAPL
    # articles in the background during dev, so a test asserting an exact
    # "articles ingested today" count against AAPL is flaky by construction
    # once the poller has ingested anything else that same day
    # (decision_log_claude.md).
    now = datetime.now(timezone.utc)
    ids = []
    for headline, symbol, published_at, ingested_at in [
        ("today TESTSYM 1", "TESTSYM", now - timedelta(hours=1), now - timedelta(hours=1)),
        ("today TESTSYM 2", "TESTSYM", now - timedelta(hours=2), now - timedelta(hours=2)),
        ("yesterday TESTSYM", "TESTSYM", now - timedelta(days=1, hours=1), now - timedelta(days=1, hours=1)),
        ("today TESTSYM2 unwatched", "TESTSYM2", now - timedelta(hours=1), now - timedelta(hours=1)),
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

    overview = stats.overview_stats(["TESTSYM"])

    assert overview.articles_ingested_today == 2  # the two today-TESTSYM articles, not TESTSYM2's or yesterday's


@pytest.fixture()
def seeded_backfilled_article(engine):
    # Real bug found live: a 30-day backfill re-run inserts old news with
    # published_at weeks in the past but ingested_at == right now (the
    # backfill call itself happened today) — counting by ingested_at made
    # "Articles ingested today" balloon to the symbol's entire article
    # history (1624) every time a backfill was re-triggered, not just
    # genuinely new same-day news (decision_log_claude.md).
    now = datetime.now(timezone.utc)
    article_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO articles (id, source, headline, published_at, ingested_at, canonical_url, normalized_headline)
                VALUES (CAST(:id AS uuid), 'finnhub', 'old news backfilled today', :published_at, :ingested_at, :url, 'old news backfilled today')
                """
            ),
            {
                "id": article_id,
                "published_at": now - timedelta(days=25),
                "ingested_at": now,
                "url": f"https://example.com/{article_id}",
            },
        )
        conn.execute(
            text("INSERT INTO article_symbols (article_id, symbol) VALUES (CAST(:id AS uuid), 'TESTSYM')"),
            {"id": article_id},
        )
    yield article_id
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM article_symbols WHERE article_id = CAST(:id AS uuid)"), {"id": article_id})
        conn.execute(text("DELETE FROM articles WHERE id = CAST(:id AS uuid)"), {"id": article_id})


def test_overview_stats_excludes_backfilled_old_news_ingested_today(engine, seeded_backfilled_article):
    stats = StatsQueries(engine)

    overview = stats.overview_stats(["TESTSYM"])

    assert overview.articles_ingested_today == 0
    assert overview.tickers_tracked == 1


@pytest.fixture()
def seeded_busiest_day_articles(engine):
    # User's exact question: "what symbol have most news in a day?" — a
    # real aggregate query the RAG chat couldn't answer (top-5 semantic
    # retrieval isn't built for counting across the whole dataset), so this
    # is answered with real SQL instead (decision_log_claude.md). TESTSYM
    # gets 3 articles on one day (the busiest), TESTSYM2 gets 2 on another
    # day and 1 on a third — TESTSYM's single day must win regardless of
    # its total across days.
    now = datetime.now(timezone.utc)
    busy_day = now - timedelta(days=2)
    other_day = now - timedelta(days=5)
    another_day = now - timedelta(days=6)
    ids = []
    for headline, symbol, published_at in [
        ("busy 1", "TESTSYM", busy_day),
        ("busy 2", "TESTSYM", busy_day),
        ("busy 3", "TESTSYM", busy_day),
        ("other 1", "TESTSYM2", other_day),
        ("other 2", "TESTSYM2", other_day),
        ("another 1", "TESTSYM2", another_day),
    ]:
        article_id = str(uuid.uuid4())
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO articles (id, source, headline, published_at, ingested_at, canonical_url, normalized_headline)
                    VALUES (CAST(:id AS uuid), 'finnhub', :headline, :published_at, now(), :url, :normalized)
                    """
                ),
                {
                    "id": article_id,
                    "headline": headline,
                    "published_at": published_at,
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


def test_busiest_symbol_day_returns_the_symbol_and_date_with_the_most_articles(engine, seeded_busiest_day_articles):
    stats = StatsQueries(engine)

    busiest = stats.busiest_symbol_day(["TESTSYM", "TESTSYM2"])

    assert busiest is not None
    assert busiest.symbol == "TESTSYM"
    assert busiest.article_count == 3


def test_busiest_symbol_day_scoped_to_watched_symbols(engine, seeded_busiest_day_articles):
    stats = StatsQueries(engine)

    busiest = stats.busiest_symbol_day(["TESTSYM2"])  # TESTSYM excluded

    assert busiest is not None
    assert busiest.symbol == "TESTSYM2"
    assert busiest.article_count == 2


def test_busiest_symbol_day_returns_none_for_no_symbols(engine):
    stats = StatsQueries(engine)

    assert stats.busiest_symbol_day([]) is None


def test_list_articles_returns_matching_articles_most_recent_first(engine, seeded_busiest_day_articles):
    # User's follow-up after the busiest-symbol-day feature: "give me all 66
    # articles" then "cant we have it query all that?" — RAG retrieval only
    # ever returns its top-5 semantically similar chunks, so a genuine
    # listing question needs a real SQL fetch of every matching article,
    # not vector search (decision_log_claude.md).
    stats = StatsQueries(engine)

    articles, total = stats.list_articles(["TESTSYM"])

    assert total == 3
    assert len(articles) == 3
    assert all(a.headline.startswith("busy") for a in articles)
    published_dates = [a.published_at for a in articles]
    assert published_dates == sorted(published_dates, reverse=True)


def test_list_articles_scoped_to_watched_symbols(engine, seeded_busiest_day_articles):
    stats = StatsQueries(engine)

    articles, total = stats.list_articles(["TESTSYM2"])

    assert total == 3  # TESTSYM2's 2 + 1, not TESTSYM's 3
    assert all(a.headline.startswith(("other", "another")) for a in articles)


def test_list_articles_reports_real_total_even_when_capped(engine, seeded_busiest_day_articles, monkeypatch):
    import infrastructure.stats_queries as stats_queries_module

    monkeypatch.setattr(stats_queries_module, "MAX_ARTICLE_LISTING", 1)
    stats = StatsQueries(engine)

    articles, total = stats.list_articles(["TESTSYM"])

    assert len(articles) == 1  # capped
    assert total == 3  # but the real total is still reported


def test_list_articles_returns_empty_for_no_symbols(engine):
    stats = StatsQueries(engine)

    assert stats.list_articles([]) == ([], 0)
