from __future__ import annotations

from celery import Celery


class CeleryBackfillQueue:
    """Enqueues tasks by name rather than importing celery_app's own task
    functions directly — the FastAPI process only needs to publish to the
    queue, not import the worker's own dependency wiring (BackfillService,
    JobTrigger, DB engine) into the request path.
    """

    def __init__(self, celery_app: Celery) -> None:
        self._celery_app = celery_app

    def enqueue_symbol_backfill(self, symbol: str) -> None:
        self._celery_app.send_task("backfill_symbol", args=[symbol], queue="backfill")

    def enqueue_symbols_backfill(self, symbols: list[str]) -> None:
        self._celery_app.send_task("backfill_symbols_older", args=[symbols], queue="backfill")

    def enqueue_symbol_news_ingested(self, symbol: str) -> None:
        self._celery_app.send_task("symbol_news_ingested", args=[symbol], queue="backfill")
