from __future__ import annotations

import httpx
import structlog
from sqlalchemy import create_engine

from application.backfill_service import BackfillService
from infrastructure.finnhub_news_client import FinnhubNewsClient
from infrastructure.local_docker_job_trigger import LocalDockerJobTrigger
from infrastructure.postgres_backfill_repo import PostgresBackfillProgressRepo
from infrastructure.processing_ingest_client import ProcessingIngestClient
from infrastructure.settings import Settings
from infrastructure.system_clock import SystemClock

logger = structlog.get_logger()


def build_backfill_service(settings: Settings) -> BackfillService:
    """Shared wiring for the pieces a symbol backfill actually needs — used
    by both the FastAPI app (for the feed's manual "load older" path) and
    the Celery worker (for the watchlist-add background task), so the two
    processes can't drift into constructing these differently.
    """
    # pool_pre_ping: celery-worker is long-lived, same stale-connection
    # exposure as query-api's engine (presentation/api.py) after a Postgres
    # restart — hit live inside a running Celery task at least once this
    # session (decision_log_claude.md's "no automatic way back" entry).
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    # 30s, not 10s — the company-news fetch genuinely got slower once the
    # backfill window widened to 30 days (a real ReadTimeout hit live at
    # 10s for a busy symbol, decision_log.md).
    finnhub_http_client = httpx.Client(timeout=30.0)
    processing_http_client = httpx.Client(timeout=30.0)
    return BackfillService(
        news_client=FinnhubNewsClient(http_client=finnhub_http_client, api_key=settings.finnhub_api_key),
        ingest_client=ProcessingIngestClient(http_client=processing_http_client, base_url=settings.processing_url),
        progress_repo=PostgresBackfillProgressRepo(engine),
        clock=SystemClock(),
    )


def build_job_trigger(settings: Settings) -> LocalDockerJobTrigger | None:
    if settings.compose_project_name:
        return LocalDockerJobTrigger(project_name=settings.compose_project_name)
    logger.warning(
        "COMPOSE_PROJECT_NAME not set — no job trigger wired, symbols added to a "
        "watchlist won't get an immediate price/feature-store backfill (the daily "
        "sweep will still pick them up)"
    )
    return None
