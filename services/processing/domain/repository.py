from __future__ import annotations

from typing import Protocol

from domain.article import Article


class UnitOfWork(Protocol):
    """One atomic transaction spanning article-insert, symbol-link, and
    embedding-write — closes the gap where a crash between separate commits
    leaves an article that exists but has no embeddings, permanently
    invisible to retrieval with no error raised (decision_log_claude.md).
    Embeddings must already be computed before entering this context: holding
    a DB transaction open across a slow external embed call would be its own
    anti-pattern (connection pool exhaustion under load).
    """

    def __enter__(self) -> "UnitOfWork": ...
    def __exit__(self, exc_type, exc_val, exc_tb) -> None: ...

    repo: "ArticleRepository"
    embedding_writer: "EmbeddingWriter"


class DedupPrecheck(Protocol):
    def find_existing(self, article: Article) -> str | None:
        """Read-only pre-check: does an article matching any tier already
        exist? Used to skip embedding entirely for an already-known article,
        without inserting or opening a write transaction. Best-effort only —
        the atomic insert_by_* calls made inside the actual transaction are
        still the source of truth for tiers 1-2 (a concurrent insert can land
        between this check and the transaction; that race is closed by the
        transaction's own ON CONFLICT DO UPDATE ... RETURNING, not by this).
        """
        ...


class ArticleRepository(Protocol):
    def find_by_fuzzy_key(self, fuzzy_key: str, exclude_article_id: str) -> str | None:
        """Return an existing article_id matching tier-3's fuzzy key, if any
        — other than exclude_article_id itself. Excluding self matters
        because this is called right after inserting the row being checked
        (its own normalized_headline/published_at already satisfy the fuzzy
        match), so without excluding it, every article would "find" itself
        and be wrongly treated as a pre-existing duplicate of itself
        (decision_log_claude.md — a real bug found via live verification).
        """
        ...

    def insert_by_canonical_url(self, article: Article) -> tuple[str, bool]:
        """Insert on canonical_url conflict-do-nothing. Returns (article_id, inserted)."""
        ...

    def insert_by_content_hash(self, article: Article, content_hash: str) -> tuple[str, bool]:
        """Insert on content_hash conflict-do-nothing. Returns (article_id, inserted)."""
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


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWork: ...
