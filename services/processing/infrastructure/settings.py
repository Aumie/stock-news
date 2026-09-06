from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/stock-news"
    embedding_model: str = "all-MiniLM-L6-v2"
    log_env: str = "dev"
