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
    llm_model: str = "claude-haiku-4-5-20251001"
    jwt_signing_secret: str = DEFAULT_JWT_SIGNING_SECRET
    log_env: str = "dev"
