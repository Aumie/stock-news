from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy.exc import OperationalError

from infrastructure.celery_app import backfill_symbol_task, backfill_symbols_older_task


def _operational_error() -> OperationalError:
    # Mirrors the real error observed live: psycopg.errors.AdminShutdown
    # surfaces through SQLAlchemy as an OperationalError when Postgres is
    # restarted mid-task (decision_log_claude.md) — a transient
    # infrastructure blip, not a bug in the task itself.
    return OperationalError("SELECT 1", {}, Exception("terminating connection due to administrator command"))


class TestBackfillSymbolTaskRetriesOnTransientDbError:
    def test_retries_on_operational_error(self) -> None:
        assert backfill_symbol_task.autoretry_for == (OperationalError,)
        assert backfill_symbol_task.retry_backoff is True
        assert backfill_symbol_task.max_retries == 3

    def test_task_raises_operational_error_when_backfill_service_fails(self) -> None:
        with patch("infrastructure.celery_app._backfill_service") as mock_service:
            mock_service.backfill_on_add.side_effect = _operational_error()
            with pytest.raises(OperationalError):
                backfill_symbol_task.run("UBER")


class TestBackfillSymbolsOlderTaskRetriesOnTransientDbError:
    def test_retries_on_operational_error(self) -> None:
        assert backfill_symbols_older_task.autoretry_for == (OperationalError,)
        assert backfill_symbols_older_task.retry_backoff is True
        assert backfill_symbols_older_task.max_retries == 3

    def test_task_raises_operational_error_when_backfill_service_fails(self) -> None:
        with patch("infrastructure.celery_app._backfill_service") as mock_service:
            mock_service.load_more_for_symbols.side_effect = _operational_error()
            with pytest.raises(OperationalError):
                backfill_symbols_older_task.run(["UBER"])
