from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/dataen"
    embedding_model: str = "all-MiniLM-L6-v2"
    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-4-5-20251001"
    log_env: str = "dev"
