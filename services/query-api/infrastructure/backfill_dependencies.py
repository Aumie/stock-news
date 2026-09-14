from __future__ import annotations

import httpx
import structlog
from sqlalchemy import create_engine

from application.backfill_service import BackfillService
from application.rebuild_debounce_service import RebuildDebounceService
from infrastructure.cloud_run_job_trigger import CloudRunJobTrigger
from infrastructure.finnhub_news_client import FinnhubNewsClient
from infrastructure.local_docker_job_trigger import LocalDockerJobTrigger
from infrastructure.postgres_backfill_repo import PostgresBackfillProgressRepo
from infrastructure.postgres_rebuild_debounce_repo import PostgresRebuildDebounceRepo
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


def build_job_trigger(settings: Settings) -> LocalDockerJobTrigger | CloudRunJobTrigger | None:
    if settings.compose_project_name:
        return LocalDockerJobTrigger(project_name=settings.compose_project_name)
    if settings.gcp_project_id:
        return CloudRunJobTrigger(project_id=settings.gcp_project_id, region=settings.gcp_region)
    logger.warning(
        "Neither COMPOSE_PROJECT_NAME nor GCP_PROJECT_ID is set — no job trigger "
        "wired, symbols added to a watchlist won't get an immediate price/"
        "feature-store backfill (the daily sweep will still pick them up)"
    )
    return None


def build_rebuild_debounce_service(
    settings: Settings, job_trigger: LocalDockerJobTrigger | CloudRunJobTrigger | None
) -> RebuildDebounceService | None:
    """Wires the "new news triggers a rebuild, but not more than once an hour
    per symbol" path (user request) — a symbol sitting on the watchlist keeps
    getting news from the poller long after it was added, and the only
    rebuild trigger before this was a 24h sweep or the one-time on-add
    trigger, so Stats could silently lag the live article count for up to a
    day (decision_log_claude.md). None when there's no job trigger to
    actually call, matching build_job_trigger's own degrade-gracefully
    pattern.
    """
    if job_trigger is None:
        return None
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    return RebuildDebounceService(
        repo=PostgresRebuildDebounceRepo(engine),
        clock=SystemClock(),
        trigger=job_trigger,
    )
