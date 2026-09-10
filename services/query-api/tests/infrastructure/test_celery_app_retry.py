from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
from sqlalchemy.exc import OperationalError

from infrastructure.celery_app import backfill_symbol_task, backfill_symbols_older_task, symbol_news_ingested_task


def _operational_error() -> OperationalError:
    # Mirrors the real error observed live: psycopg.errors.AdminShutdown
    # surfaces through SQLAlchemy as an OperationalError when Postgres is
    # restarted mid-task (decision_log_claude.md) — a transient
    # infrastructure blip, not a bug in the task itself.
    return OperationalError("SELECT 1", {}, Exception("terminating connection due to administrator command"))


def _connect_error() -> httpx.ConnectError:
    # Mirrors a real error found live: a fresh stack start hit
    # backfill_symbol before `processing` had finished starting up
    # (decision_log_claude.md) — a transient startup-ordering blip, not a
    # bug in the task itself.
    return httpx.ConnectError("[Errno 111] Connection refused")


class TestBackfillSymbolTaskRetriesOnTransientDbError:
    def test_retries_on_operational_error(self) -> None:
        assert backfill_symbol_task.autoretry_for == (OperationalError, httpx.TransportError)
        assert backfill_symbol_task.retry_backoff is True
        assert backfill_symbol_task.max_retries == 3

    def test_task_raises_operational_error_when_backfill_service_fails(self) -> None:
        with patch("infrastructure.celery_app._backfill_service") as mock_service:
            mock_service.backfill_on_add.side_effect = _operational_error()
            with pytest.raises(OperationalError):
                backfill_symbol_task.run("UBER")

    def test_task_raises_connect_error_when_processing_is_unreachable(self) -> None:
        with patch("infrastructure.celery_app._backfill_service") as mock_service:
            mock_service.backfill_on_add.side_effect = _connect_error()
            with pytest.raises(httpx.ConnectError):
                backfill_symbol_task.run("TSLA")


class TestBackfillSymbolsOlderTaskRetriesOnTransientDbError:
    def test_retries_on_operational_error(self) -> None:
        assert backfill_symbols_older_task.autoretry_for == (OperationalError, httpx.TransportError)
        assert backfill_symbols_older_task.retry_backoff is True
        assert backfill_symbols_older_task.max_retries == 3

    def test_task_raises_operational_error_when_backfill_service_fails(self) -> None:
        with patch("infrastructure.celery_app._backfill_service") as mock_service:
            mock_service.load_more_for_symbols.side_effect = _operational_error()
            with pytest.raises(OperationalError):
                backfill_symbols_older_task.run(["UBER"])


class TestSymbolNewsIngestedTaskRetriesOnTransientDbError:
    # Real bug found live: this task's own debounce-state write hit exactly
    # the same transient-Postgres-restart failure the other two tasks were
    # already protected against, but this task had no retry configured yet
    # when it shipped — caught during live verification of the debounced
    # rebuild-trigger feature itself, not by a test (decision_log_claude.md).
    def test_retries_on_operational_error(self) -> None:
        assert symbol_news_ingested_task.autoretry_for == (OperationalError,)
        assert symbol_news_ingested_task.retry_backoff is True
        assert symbol_news_ingested_task.max_retries == 3

    def test_task_raises_operational_error_when_debounce_service_fails(self) -> None:
        with patch("infrastructure.celery_app._rebuild_debounce_service") as mock_service:
            mock_service.notify_symbol_has_new_news.side_effect = _operational_error()
            with pytest.raises(OperationalError):
                symbol_news_ingested_task.run("TSLA")
