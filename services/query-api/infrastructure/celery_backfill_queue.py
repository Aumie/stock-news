from __future__ import annotations

import structlog
from celery import Celery
from kombu.exceptions import OperationalError

logger = structlog.get_logger()


class CeleryBackfillQueue:
    """Enqueues tasks by name rather than importing celery_app's own task
    functions directly — the FastAPI process only needs to publish to the
    queue, not import the worker's own dependency wiring (BackfillService,
    JobTrigger, DB engine) into the request path.
    """

    def __init__(self, celery_app: Celery) -> None:
        self._celery_app = celery_app

    def _send(self, task_name: str, **kwargs) -> None:
        # Real deploy failure found live: Cloud Run's query-api has no
        # RabbitMQ broker deployed yet (deliberately deferred, per this
        # file's own project-level scope), so send_task raised an unhandled
        # kombu ConnectionError that failed the entire request — even though
        # every caller here already treats a failed enqueue as best-effort
        # (e.g. WatchlistService.add_symbol's own comment: "a failed
        # background step only logs a warning, it never surfaces back to the
        # original request, since the symbol is already saved by the time
        # either step runs", api-spec.md §4.1). Catching it here, once,
        # keeps every call site's already-correct assumption true instead of
        # needing a try/except at each of the four call sites.
        try:
            self._celery_app.send_task(task_name, queue="backfill", **kwargs)
        except OperationalError:
            logger.warning("celery_backfill_queue.enqueue_failed", task_name=task_name, exc_info=True)

    def enqueue_symbol_backfill(self, symbol: str) -> None:
        self._send("backfill_symbol", args=[symbol])

    def enqueue_symbols_backfill(self, symbols: list[str]) -> None:
        self._send("backfill_symbols_older", args=[symbols])

    def enqueue_symbol_news_ingested(self, symbol: str) -> None:
        self._send("symbol_news_ingested", args=[symbol])

    def enqueue_daily_batch_sweep(self) -> None:
        self._send("daily_batch_sweep")
