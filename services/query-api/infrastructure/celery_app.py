from __future__ import annotations

import structlog
from celery import Celery
from kombu import Queue
from sqlalchemy.exc import OperationalError

from infrastructure.backfill_dependencies import build_backfill_service, build_job_trigger
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

# Built once per worker process, not per task — a task can run many times
# in the same worker without re-establishing DB/HTTP clients each time,
# matching how api.py builds these once at FastAPI startup rather than per
# request.
_backfill_service = build_backfill_service(settings)
_job_trigger = build_job_trigger(settings)


# Real bug found live: a Postgres restart mid-task (recurring Docker Desktop
# instability this project has hit repeatedly) raised OperationalError
# (psycopg.errors.AdminShutdown) inside backfill_on_add, and with no retry
# configured the task simply died — the symbol was left permanently stuck
# showing "still backfilling" with nothing left to ever complete it
# (decision_log_claude.md). autoretry_for only covers this specific
# transient-infrastructure error, not genuine bugs — those should still
# surface immediately rather than being retried into a longer failure.
@celery_app.task(
    name="backfill_symbol",
    autoretry_for=(OperationalError,),
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
    autoretry_for=(OperationalError,),
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
