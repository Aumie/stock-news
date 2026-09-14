from unittest.mock import MagicMock

from kombu.exceptions import OperationalError

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


def test_enqueue_symbol_news_ingested_sends_the_symbol_news_ingested_task():
    celery_app = MagicMock()
    queue = CeleryBackfillQueue(celery_app)

    queue.enqueue_symbol_news_ingested("AAPL")

    celery_app.send_task.assert_called_once_with("symbol_news_ingested", args=["AAPL"], queue="backfill")


def test_enqueue_daily_batch_sweep_sends_the_daily_batch_sweep_task():
    celery_app = MagicMock()
    queue = CeleryBackfillQueue(celery_app)

    queue.enqueue_daily_batch_sweep()

    celery_app.send_task.assert_called_once_with("daily_batch_sweep", queue="backfill")


def test_enqueue_symbol_backfill_swallows_a_broker_connection_failure():
    # Real deploy failure found live: Cloud Run's query-api has no RabbitMQ
    # broker deployed, and send_task raising kombu's OperationalError used
    # to fail the whole /watchlist request even though the symbol was
    # already saved — every caller already treats a failed enqueue as
    # best-effort, so this must not raise.
    celery_app = MagicMock()
    celery_app.send_task.side_effect = OperationalError("Connection refused")
    queue = CeleryBackfillQueue(celery_app)

    queue.enqueue_symbol_backfill("AAPL")
