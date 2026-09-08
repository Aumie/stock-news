"""Live check against real Postgres: symbol_backfill_progress upserts
idempotently and the repo returns None for a symbol never backfilled.

Requires `docker compose up postgres`.
"""

from __future__ import annotations

import os
from datetime import date

import pytest
from sqlalchemy import create_engine, text

from infrastructure.postgres_backfill_repo import PostgresBackfillProgressRepo

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
        conn.execute(text("DELETE FROM symbol_backfill_progress WHERE symbol = 'TESTSYM'"))
    yield engine
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM symbol_backfill_progress WHERE symbol = 'TESTSYM'"))


def test_get_earliest_backfilled_returns_none_when_never_backfilled(engine):
    repo = PostgresBackfillProgressRepo(engine)

    assert repo.get_earliest_backfilled("TESTSYM") is None


def test_set_then_get_returns_the_date(engine):
    repo = PostgresBackfillProgressRepo(engine)

    repo.set_earliest_backfilled("TESTSYM", date(2026, 9, 6))

    assert repo.get_earliest_backfilled("TESTSYM") == date(2026, 9, 6)


def test_set_is_idempotent_and_updates_on_conflict(engine):
    repo = PostgresBackfillProgressRepo(engine)

    repo.set_earliest_backfilled("TESTSYM", date(2026, 9, 6))
    repo.set_earliest_backfilled("TESTSYM", date(2026, 8, 23))

    assert repo.get_earliest_backfilled("TESTSYM") == date(2026, 8, 23)
