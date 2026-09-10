from __future__ import annotations

from typing import Protocol

from domain.article import Article
from domain.dedup import content_hash, fuzzy_key
from domain.repository import ArticleRepository, Chunker, DedupPrecheck, Embedder, UnitOfWorkFactory


class NewsIngestedNotifier(Protocol):
    def notify_symbol_news_ingested(self, symbol: str) -> None: ...


class ProcessArticleUseCase:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        dedup_precheck: DedupPrecheck,
        chunker: Chunker,
        embedder: Embedder,
        news_ingested_notifier: NewsIngestedNotifier | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._dedup_precheck = dedup_precheck
        self._chunker = chunker
        self._embedder = embedder
        self._news_ingested_notifier = news_ingested_notifier

    def process(self, article: Article, symbol: str) -> str:
        # Two-phase: a cheap, read-only dedup check first (outside any
        # transaction) skips embedding entirely for an already-known article,
        # preserving §4.3's "no re-embed on a cross-match" guarantee. Only a
        # genuinely new article reaches the embed call. The short atomic
        # transaction afterward still re-verifies uniqueness via its own
        # ON CONFLICT DO UPDATE ... RETURNING, closing the remaining race
        # where a concurrent insert lands between this check and that
        # transaction — in that rare case the just-computed embeddings are
        # simply discarded rather than written (decision_log_claude.md).
        existing_id = self._dedup_precheck.find_existing(article)
        if existing_id is not None:
            with self._uow_factory() as uow:
                uow.repo.add_symbol(existing_id, symbol)
            self._notify_symbol_news_ingested(symbol)
            return existing_id

        chunks = self._chunker.chunk(article.content)
        vectors = self._embedder.embed(chunks) if chunks else []

        with self._uow_factory() as uow:
            article_id, is_new = self._resolve_article(uow.repo, article)
            uow.repo.add_symbol(article_id, symbol)
            if is_new and chunks:
                uow.embedding_writer.write(article_id, chunks, vectors)
        self._notify_symbol_news_ingested(symbol)
        return article_id

    def _notify_symbol_news_ingested(self, symbol: str) -> None:
        # Every successful call means this symbol just gained a new article
        # association — whether the article itself was brand new or a
        # cross-source dedup match, the symbol's own news picture changed
        # either way, so daily_symbol_features may now be stale for it
        # (user request: "if there is new news from polling it should
        # trigger so it match the number", decision_log_claude.md).
        if self._news_ingested_notifier is not None:
            self._news_ingested_notifier.notify_symbol_news_ingested(symbol)

    def _resolve_article(self, repo: ArticleRepository, article: Article) -> tuple[str, bool]:
        if article.canonical_url:
            article_id, inserted = repo.insert_by_canonical_url(article)
            return article_id, inserted

        hash_value = content_hash(article)
        article_id, inserted = repo.insert_by_content_hash(article, hash_value)
        if not inserted:
            return article_id, False

        key = fuzzy_key(article)
        existing_id = repo.find_by_fuzzy_key(key, exclude_article_id=article_id)
        if existing_id is not None:
            return existing_id, False

        repo.register_fuzzy_key(article_id, key)
        return article_id, True
