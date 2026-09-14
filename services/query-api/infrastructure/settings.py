from __future__ import annotations

from pydantic_settings import BaseSettings

# Shared literal with services/auth's main.go default — if this string is
# still in effect at startup, HS256 is symmetric and total auth bypass is
# possible for anyone who has read this public source (decision_log_claude.md).
DEFAULT_JWT_SIGNING_SECRET = "dev-secret-change-me"


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/stock-news"
    embedding_model: str = "all-MiniLM-L6-v2"
    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-4-5"
    jwt_signing_secret: str = DEFAULT_JWT_SIGNING_SECRET
    finnhub_api_key: str = ""
    processing_url: str = "http://localhost:8001"
    log_env: str = "dev"
    # Local-dev only — selects LocalDockerJobTrigger when set (docker-compose.yml
    # pins this to "stock-news"). Unset in the cloud image, where
    # gcp_project_id selects CloudRunJobTrigger instead (decision_log.md).
    compose_project_name: str = ""
    # RabbitMQ broker for Celery's watchlist-add backfill task queue — a
    # local docker-compose service here, CloudAMQP's free "Little Lemur"
    # tier at the milestone 7 cloud migration (decision_log.md).
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672//"
    # Cloud-only — selects CloudRunJobTrigger when set (Terraform sets this
    # to the real GCP project ID for query-api's Cloud Run deployment). Empty
    # locally, where compose_project_name selects LocalDockerJobTrigger
    # instead; build_job_trigger() checks compose_project_name first, so both
    # being set at once (shouldn't happen) still resolves predictably.
    gcp_project_id: str = ""
    gcp_region: str = "us-central1"
