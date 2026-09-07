"""Live check against a real Postgres (docs/milestone.md §5): confirms bars
upsert idempotently into `prices` (append-only per symbol/date, but a re-run
of the same trading day must not fail or duplicate — see decision_log.md's
"`prices` is append-only, no rolling deletion").

Requires `docker compose up postgres`. Skips if unreachable, matching this
project's established integration-test pattern (services/processing/tests/integration).
"""

from __future__ import annotations

import os
from datetime import date

import psycopg
import pytest

from prices.prices_repo import PostgresPricesRepository
from prices.yahoo_client import DailyBar

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/stock-news"
)


@pytest.fixture
def conn():
    try:
        conn = psycopg.connect(DATABASE_URL)
    except psycopg.OperationalError as exc:
        pytest.skip(f"Postgres not reachable at {DATABASE_URL}: {exc}")
    conn.execute("DELETE FROM prices WHERE symbol = 'TESTSYM'")
    conn.commit()
    yield conn
    conn.execute("DELETE FROM prices WHERE symbol = 'TESTSYM'")
    conn.commit()
    conn.close()


def test_upsert_bars_inserts_new_rows(conn):
    repo = PostgresPricesRepository(conn)
    bars = [
        DailyBar(date=date(2026, 9, 18), open=100.0, high=105.0, low=99.0, close=103.0, volume=1000),
        DailyBar(date=date(2026, 9, 19), open=103.0, high=110.0, low=102.0, close=108.0, volume=1500),
    ]

    repo.upsert_bars("TESTSYM", bars)
    conn.commit()

    rows = conn.execute(
        "SELECT date, open, high, low, close, volume FROM prices WHERE symbol = %s ORDER BY date",
        ("TESTSYM",),
    ).fetchall()
    assert len(rows) == 2
    assert rows[0][0] == date(2026, 9, 18)
    assert rows[0][4] == 103.0


def test_upsert_bars_is_idempotent_on_rerun(conn):
    repo = PostgresPricesRepository(conn)
    bar = DailyBar(date=date(2026, 9, 18), open=100.0, high=105.0, low=99.0, close=103.0, volume=1000)

    repo.upsert_bars("TESTSYM", [bar])
    conn.commit()
    # Same day re-run with a revised close (e.g. a late correction) — must
    # update in place, not error or create a second row.
    revised = DailyBar(date=date(2026, 9, 18), open=100.0, high=106.0, low=99.0, close=104.5, volume=1200)
    repo.upsert_bars("TESTSYM", [revised])
    conn.commit()

    rows = conn.execute(
        "SELECT close, volume FROM prices WHERE symbol = %s AND date = %s",
        ("TESTSYM", date(2026, 9, 18)),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 104.5
    assert rows[0][1] == 1200
