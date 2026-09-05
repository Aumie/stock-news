from __future__ import annotations

from domain.article import Article
from domain.dedup import content_hash, fuzzy_key
from domain.repository import ArticleRepository, Chunker, Embedder, EmbeddingWriter


class ProcessArticleUseCase:
    def __init__(
        self,
        repo: ArticleRepository,
        chunker: Chunker,
        embedder: Embedder,
        embedding_writer: EmbeddingWriter,
    ) -> None:
        self._repo = repo
        self._chunker = chunker
        self._embedder = embedder
        self._embedding_writer = embedding_writer

    def process(self, article: Article, symbol: str) -> str:
        article_id, is_new = self._resolve_article(article)
        self._repo.add_symbol(article_id, symbol)
        if is_new:
            self._chunk_and_embed(article_id, article.content)
        return article_id

    def _resolve_article(self, article: Article) -> tuple[str, bool]:
        if article.canonical_url:
            article_id, inserted = self._repo.insert_by_canonical_url(article)
            return article_id, inserted

        hash_value = content_hash(article)
        article_id, inserted = self._repo.insert_by_content_hash(article, hash_value)
        if not inserted:
            return article_id, False

        key = fuzzy_key(article)
        existing_id = self._repo.find_by_fuzzy_key(key)
        if existing_id is not None:
            return existing_id, False

        self._repo.register_fuzzy_key(article_id, key)
        return article_id, True

    def _chunk_and_embed(self, article_id: str, content: str) -> None:
        chunks = self._chunker.chunk(content)
        vectors = self._embedder.embed(chunks)
        self._embedding_writer.write(article_id, chunks, vectors)
