"""Live check for milestone 6 (docs/milestone.md §6): confirms watchlist
add/list/remove against real Postgres, including the idempotent re-add path
(matches DELETE's stated idempotency, api-spec.md).

Requires `docker compose up postgres`.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, text

from infrastructure.postgres_watchlist_repo import PostgresWatchlistRepository

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
    yield engine


@pytest.fixture
def user_id(engine):
    uid = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO users (id, google_sub, email) VALUES (CAST(:id AS uuid), :sub, :email)"),
            {"id": uid, "sub": f"test-sub-{uid}", "email": f"{uid}@example.com"},
        )
    yield uid
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM watchlist WHERE user_id = CAST(:id AS uuid)"), {"id": uid})
        conn.execute(text("DELETE FROM users WHERE id = CAST(:id AS uuid)"), {"id": uid})


def test_add_then_list_returns_the_symbol(engine, user_id):
    repo = PostgresWatchlistRepository(engine)

    entry = repo.add(user_id, "AAPL")

    assert entry.symbol == "AAPL"
    assert [e.symbol for e in repo.list_for_user(user_id)] == ["AAPL"]


def test_add_is_idempotent_on_duplicate(engine, user_id):
    repo = PostgresWatchlistRepository(engine)

    repo.add(user_id, "AAPL")
    repo.add(user_id, "AAPL")  # does not raise a primary-key violation

    assert [e.symbol for e in repo.list_for_user(user_id)] == ["AAPL"]


def test_remove_deletes_and_is_idempotent(engine, user_id):
    repo = PostgresWatchlistRepository(engine)
    repo.add(user_id, "AAPL")

    repo.remove(user_id, "AAPL")
    repo.remove(user_id, "AAPL")  # does not raise

    assert repo.list_for_user(user_id) == []


def test_list_is_scoped_to_the_calling_user(engine, user_id):
    repo = PostgresWatchlistRepository(engine)
    other_user_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO users (id, google_sub, email) VALUES (CAST(:id AS uuid), :sub, :email)"),
            {"id": other_user_id, "sub": f"test-sub-{other_user_id}", "email": f"{other_user_id}@example.com"},
        )
    try:
        repo.add(user_id, "AAPL")
        repo.add(other_user_id, "MSFT")

        assert [e.symbol for e in repo.list_for_user(user_id)] == ["AAPL"]
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM watchlist WHERE user_id = CAST(:id AS uuid)"), {"id": other_user_id})
            conn.execute(text("DELETE FROM users WHERE id = CAST(:id AS uuid)"), {"id": other_user_id})
