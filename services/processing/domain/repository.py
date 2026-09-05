from __future__ import annotations

from typing import Protocol

from domain.article import Article


class ArticleRepository(Protocol):
    def insert_by_canonical_url(self, article: Article) -> tuple[str, bool]:
        """Insert on canonical_url conflict-do-nothing. Returns (article_id, inserted)."""
        ...

    def insert_by_content_hash(self, article: Article, content_hash: str) -> tuple[str, bool]:
        """Insert on content_hash conflict-do-nothing. Returns (article_id, inserted)."""
        ...

    def find_by_fuzzy_key(self, fuzzy_key: str) -> str | None:
        """Return an existing article_id matching tier-3's fuzzy key, if any."""
        ...

    def register_fuzzy_key(self, article_id: str, fuzzy_key: str) -> None:
        """Record this article's fuzzy key so a later cross-source poll can match it.

        Best-effort only (§4.3: tier 3 can't be a hard DB constraint) — a rare
        concurrent race can still produce a near-duplicate row; not closed in v1.
        """
        ...

    def add_symbol(self, article_id: str, symbol: str) -> None:
        """Idempotent insert into article_symbols (ON CONFLICT DO NOTHING)."""
        ...


class EmbeddingWriter(Protocol):
    def write(self, article_id: str, chunks: list[str], vectors: list[list[float]]) -> None: ...


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class Chunker(Protocol):
    def chunk(self, text: str) -> list[str]: ...
