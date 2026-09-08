from unittest.mock import MagicMock

from infrastructure.celery_backfill_queue import CeleryBackfillQueue


def test_enqueue_symbol_backfill_sends_the_backfill_symbol_task():
    celery_app = MagicMock()
    queue = CeleryBackfillQueue(celery_app)

    queue.enqueue_symbol_backfill("AAPL")

    celery_app.send_task.assert_called_once_with("backfill_symbol", args=["AAPL"], queue="backfill")


def test_enqueue_symbols_backfill_sends_the_backfill_symbols_older_task():
    celery_app = MagicMock()
    queue = CeleryBackfillQueue(celery_app)

    queue.enqueue_symbols_backfill(["AAPL", "MSFT"])

    celery_app.send_task.assert_called_once_with("backfill_symbols_older", args=[["AAPL", "MSFT"]], queue="backfill")
