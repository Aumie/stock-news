from __future__ import annotations

import httpx
import structlog
from celery import Celery
from celery.signals import beat_init
from kombu import Queue
from sqlalchemy.exc import OperationalError

from infrastructure.backfill_dependencies import (
    build_backfill_service,
    build_job_trigger,
    build_rebuild_debounce_service,
)
from infrastructure.logging import configure_logging
from infrastructure.settings import Settings

settings = Settings()
configure_logging(settings.log_env)
logger = structlog.get_logger()

celery_app = Celery("query_api", broker=settings.rabbitmq_url)
celery_app.conf.task_default_queue = "backfill"
# Explicit durable queue, not kombu's transient+non-exclusive default —
# RabbitMQ 4.x has deprecated that pattern and rejects it outright
# (INTERNAL_ERROR: transient_nonexcl_queues), confirmed live. Durable is the
# RabbitMQ team's own recommended alternative, and it's a client-side
# setting that works identically on a self-hosted broker or CloudAMQP's
# shared plan — no server-side config access needed either way
# (decision_log.md).
celery_app.conf.task_queues = (Queue("backfill", durable=True),)
# Single-worker local/small-cloud setup — mingle/gossip exist to coordinate
# multiple workers and declare their own transient queues under the hood,
# which would hit the same deprecation. Not needed here.
celery_app.conf.worker_enable_remote_control = False
celery_app.conf.worker_send_task_events = False
# Self-healing daily-batch sweep, not just the on-add trigger — real bug
# found live: daily_symbol_features is a dbt `table` materialization (full
# drop + rebuild on every run), and the only thing that ever ran the job was
# a watchlist-add event. A Docker/Postgres restart mid-run left the table
# missing with nothing to rebuild it until a symbol was next added
# (decision_log_claude.md). daily_batch/main.py already had a whole-watchlist
# sweep mode built in (no --symbol) that nothing was scheduling — this wires
# it up instead of duplicating that logic. 24h matches the job's own name and
# the daily grain of the data it produces; more frequent buys nothing since
# article_count/price_close are per-calendar-day.
celery_app.conf.beat_schedule = {
    "daily-batch-sweep": {
        "task": "daily_batch_sweep",
        "schedule": 60 * 60 * 24,
    },
}

# Built once per worker process, not per task — a task can run many times
# in the same worker without re-establishing DB/HTTP clients each time,
# matching how api.py builds these once at FastAPI startup rather than per
# request.
_backfill_service = build_backfill_service(settings)
_job_trigger = build_job_trigger(settings)
_rebuild_debounce_service = build_rebuild_debounce_service(settings, _job_trigger)


# Real bug found live: a Postgres restart mid-task (recurring Docker Desktop
# instability this project has hit repeatedly) raised OperationalError
# (psycopg.errors.AdminShutdown) inside backfill_on_add, and with no retry
# configured the task simply died — the symbol was left permanently stuck
# showing "still backfilling" with nothing left to ever complete it
# (decision_log_claude.md). autoretry_for only covers this specific
# transient-infrastructure error, not genuine bugs — those should still
# surface immediately rather than being retried into a longer failure.
# httpx.TransportError added after a second, related failure found live: a
# fresh stack start hit backfill_symbol before `processing` had finished
# starting up, raising httpx.ConnectError with no retry either — same class
# of transient-startup-ordering issue, different dependency.
@celery_app.task(
    name="backfill_symbol",
    autoretry_for=(OperationalError, httpx.TransportError),
    retry_backoff=True,
    max_retries=3,
)
def backfill_symbol_task(symbol: str) -> None:
    logger.info("celery.backfill_symbol.starting", symbol=symbol)
    _backfill_service.backfill_on_add(symbol)
    if _job_trigger is not None:
        _job_trigger.trigger_for_symbol(symbol)
    logger.info("celery.backfill_symbol.complete", symbol=symbol)


@celery_app.task(
    name="backfill_symbols_older",
    autoretry_for=(OperationalError, httpx.TransportError),
    retry_backoff=True,
    max_retries=3,
)
def backfill_symbols_older_task(symbols: list[str]) -> None:
    # One "load older" window per symbol, not the old synchronous
    # up-to-6-attempts loop — the Live Feed's "load older" click enqueues
    # this and returns immediately; the user re-checks (another click) for
    # newly-arrived results rather than the request blocking on however
    # long Finnhub takes (decision_log.md).
    logger.info("celery.backfill_symbols_older.starting", symbols=symbols)
    _backfill_service.load_more_for_symbols(symbols)
    logger.info("celery.backfill_symbols_older.complete", symbols=symbols)


@celery_app.task(name="daily_batch_sweep")
def daily_batch_sweep_task() -> None:
    logger.info("celery.daily_batch_sweep.starting")
    if _job_trigger is not None:
        _job_trigger.trigger_full_sweep()
    logger.info("celery.daily_batch_sweep.complete")


@celery_app.task(
    name="symbol_news_ingested",
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    max_retries=3,
)
def symbol_news_ingested_task(symbol: str) -> None:
    # Triggered by processing after every successful ingest (user request:
    # "if there is new news from polling it should trigger so it match the
    # number") — debounced to at most once per hour per symbol so a burst of
    # articles (a real one hit TSLA: 6 articles in ~14 minutes) doesn't turn
    # into a burst of full-table dbt rebuilds (decision_log_claude.md).
    if _rebuild_debounce_service is None:
        return
    triggered = _rebuild_debounce_service.notify_symbol_has_new_news(symbol)
    logger.info("celery.symbol_news_ingested.handled", symbol=symbol, triggered=triggered)


@beat_init.connect
def _run_sweep_on_beat_startup(**kwargs: object) -> None:
    # Celery Beat's interval schedule waits a full 24h before its first fire
    # (confirmed against Celery's own documented behavior, not assumed) — so
    # without this, a container that just came up with a missing
    # daily_symbol_features table would still sit broken for up to a day
    # before self-healing. Firing once on Beat's own startup, in addition to
    # the recurring 24h schedule, covers both the "just deployed/restarted"
    # case and the steady-state case.
    daily_batch_sweep_task.delay()
