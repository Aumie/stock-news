from datetime import datetime

import pytest

from application.process_article import ProcessArticleUseCase
from domain.article import Article


class FakeRepo:
    def __init__(self):
        self.by_url: dict[str, str] = {}
        self.by_hash: dict[str, str] = {}
        self.by_fuzzy: dict[str, str] = {}
        self.symbols: set[tuple[str, str]] = set()
        self._next_id = 0

    def _new_id(self) -> str:
        self._next_id += 1
        return f"article-{self._next_id}"

    def insert_by_canonical_url(self, article):
        if article.canonical_url in self.by_url:
            return self.by_url[article.canonical_url], False
        article_id = self._new_id()
        self.by_url[article.canonical_url] = article_id
        return article_id, True

    def insert_by_content_hash(self, article, content_hash):
        if content_hash in self.by_hash:
            return self.by_hash[content_hash], False
        article_id = self._new_id()
        self.by_hash[content_hash] = article_id
        return article_id, True

    def register_fuzzy_key(self, article_id, fuzzy_key):
        self.by_fuzzy.setdefault(fuzzy_key, article_id)

    def find_by_fuzzy_key(self, fuzzy_key):
        return self.by_fuzzy.get(fuzzy_key)

    def add_symbol(self, article_id, symbol):
        self.symbols.add((article_id, symbol))


class FakeChunker:
    def chunk(self, text):
        return [text]


class FakeEmbedder:
    def __init__(self):
        self.embed_calls = 0

    def embed(self, texts):
        self.embed_calls += 1
        return [[0.1, 0.2] for _ in texts]


class FakeEmbeddingWriter:
    def __init__(self):
        self.writes = []

    def write(self, article_id, chunks, vectors):
        self.writes.append((article_id, chunks, vectors))


def _article(**overrides) -> Article:
    defaults = dict(
        source="finnhub",
        headline="Apple unveils new iPhone",
        published_at=datetime(2026, 9, 4, 14, 30, 0),
        content="body text",
        canonical_url=None,
    )
    defaults.update(overrides)
    return Article(**defaults)


@pytest.fixture
def use_case():
    repo = FakeRepo()
    chunker = FakeChunker()
    embedder = FakeEmbedder()
    writer = FakeEmbeddingWriter()
    uc = ProcessArticleUseCase(repo=repo, chunker=chunker, embedder=embedder, embedding_writer=writer)
    return uc, repo, embedder, writer


class TestNewArticle:
    def test_brand_new_article_gets_chunked_and_embedded(self, use_case):
        uc, repo, embedder, writer = use_case
        article = _article(canonical_url="https://example.com/1")

        uc.process(article, symbol="AAPL")

        assert embedder.embed_calls == 1
        assert len(writer.writes) == 1
        assert ("article-1", "AAPL") in repo.symbols


class TestTier1CanonicalUrl:
    def test_same_url_is_not_reembedded(self, use_case):
        uc, repo, embedder, writer = use_case
        a = _article(canonical_url="https://example.com/1")
        b = _article(canonical_url="https://example.com/1", headline="different headline entirely")

        uc.process(a, symbol="AAPL")
        uc.process(b, symbol="MSFT")

        assert embedder.embed_calls == 1
        assert len(writer.writes) == 1
        assert ("article-1", "AAPL") in repo.symbols
        assert ("article-1", "MSFT") in repo.symbols


class TestTier2ContentHash:
    def test_same_hash_no_url_is_not_reembedded(self, use_case):
        uc, repo, embedder, writer = use_case
        a = _article(canonical_url=None, published_at=datetime(2026, 9, 4, 14, 30, 0))
        b = _article(canonical_url=None, published_at=datetime(2026, 9, 4, 14, 30, 45))

        uc.process(a, symbol="AAPL")
        uc.process(b, symbol="AAPL")

        assert embedder.embed_calls == 1


class TestTier3FuzzyCrossSource:
    def test_cross_source_same_day_and_headline_matches_without_reembedding(self, use_case):
        uc, repo, embedder, writer = use_case
        a = _article(source="finnhub", canonical_url=None, headline="Apple unveils new iPhone")
        b = _article(source="marketaux", canonical_url=None, headline="Apple Unveils New iPhone!")

        uc.process(a, symbol="AAPL")
        uc.process(b, symbol="AAPL")

        assert embedder.embed_calls == 1

    def test_new_symbol_association_added_on_fuzzy_match(self, use_case):
        uc, repo, embedder, writer = use_case
        a = _article(source="finnhub", canonical_url=None, headline="Apple unveils new iPhone")
        b = _article(source="marketaux", canonical_url=None, headline="Apple Unveils New iPhone!")

        uc.process(a, symbol="AAPL")
        uc.process(b, symbol="MSFT")

        assert ("article-1", "AAPL") in repo.symbols
        assert ("article-1", "MSFT") in repo.symbols
