from __future__ import annotations

from sqlalchemy.engine import Engine

from infrastructure.embedding_writer import PostgresEmbeddingWriter
from infrastructure.postgres_repo import PostgresArticleRepository


class PostgresUnitOfWork:
    """One transaction shared by repo + embedding_writer for the duration of
    the `with` block — see domain/repository.py's UnitOfWork protocol for why.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def __enter__(self) -> "PostgresUnitOfWork":
        self._ctx = self._engine.begin()
        conn = self._ctx.__enter__()
        self.repo = PostgresArticleRepository(conn)
        self.embedding_writer = PostgresEmbeddingWriter(conn)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._ctx.__exit__(exc_type, exc_val, exc_tb)
