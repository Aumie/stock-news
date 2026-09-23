from datetime import datetime

import pytest

from application.process_article import ProcessArticleUseCase
from domain.article import Article
from domain.dedup import content_hash, fuzzy_key
from domain.validation import ArticleValidationError


class FakeRepo:
    """Models a single shared "articles" table, like real Postgres — a row
    inserted by insert_by_content_hash is immediately visible to
    find_by_fuzzy_key (same row, same normalized_headline/published_at),
    NOT a separate registration step. Modeling these as independent dicts
    previously hid a real bug: find_by_fuzzy_key matched a row against
    itself right after insert, marking every new article a "duplicate"
    (decision_log_claude.md — found via live verification, not by this
    fixture, which is exactly the problem this fixture design fixes).
    """

    def __init__(self):
        self.by_url: dict[str, str] = {}
        self.by_hash: dict[str, str] = {}
        self.rows: dict[str, tuple[str, str]] = {}  # article_id -> (fuzzy_key, ...)
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
        self.rows[article_id] = fuzzy_key(article)
        return article_id, True

    def insert_by_content_hash(self, article, content_hash):
        if content_hash in self.by_hash:
            return self.by_hash[content_hash], False
        article_id = self._new_id()
        self.by_hash[content_hash] = article_id
        self.rows[article_id] = fuzzy_key(article)
        return article_id, True

    def register_fuzzy_key(self, article_id, fuzzy_key):
        pass  # no-op here too, matching PostgresArticleRepository — see its own comment

    def find_by_fuzzy_key(self, fuzzy_key, exclude_article_id):
        for article_id, key in self.rows.items():
            if article_id != exclude_article_id and key == fuzzy_key:
                return article_id
        return None

    def add_symbol(self, article_id, symbol):
        self.symbols.add((article_id, symbol))


class FakeDedupPrecheck:
    """Mirrors FakeRepo's known-article state so the pre-check phase sees the
    same world the transactional insert calls would.
    """

    def __init__(self, repo: "FakeRepo"):
        self._repo = repo

    def find_existing(self, article):
        if article.canonical_url:
            return self._repo.by_url.get(article.canonical_url)

        existing = self._repo.by_hash.get(content_hash(article))
        if existing is not None:
            return existing

        key = fuzzy_key(article)
        for article_id, row_key in self._repo.rows.items():
            if row_key == key:
                return article_id
        return None


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


class FakeUnitOfWork:
    """Mirrors PostgresUnitOfWork's __enter__/__exit__ contract, but backed by
    a single shared FakeRepo/FakeEmbeddingWriter instead of a real transaction
    — enough to exercise ProcessArticleUseCase's UnitOfWork usage without a DB.
    """

    def __init__(self, repo, embedding_writer):
        self.repo = repo
        self.embedding_writer = embedding_writer

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


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


class FakeNewsIngestedNotifier:
    def __init__(self) -> None:
        self.notified_for: list[str] = []

    def notify_symbol_news_ingested(self, symbol: str) -> None:
        self.notified_for.append(symbol)


@pytest.fixture
def use_case():
    repo = FakeRepo()
    chunker = FakeChunker()
    embedder = FakeEmbedder()
    writer = FakeEmbeddingWriter()
    uc = ProcessArticleUseCase(
        uow_factory=lambda: FakeUnitOfWork(repo, writer),
        dedup_precheck=FakeDedupPrecheck(repo),
        chunker=chunker,
        embedder=embedder,
    )
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
    def test_brand_new_article_with_no_url_still_gets_embedded(self, use_case):
        # Regression guard: find_by_fuzzy_key must exclude the article's own
        # just-inserted row, or every URL-less article "matches itself" via
        # tier 3 and never gets embedded at all — a real, previously-shipped
        # bug that only affects the no-canonical-url path (canonical-url
        # articles never call find_by_fuzzy_key), found via live verification
        # against real Postgres, not by any unit test at the time
        # (decision_log_claude.md).
        uc, repo, embedder, writer = use_case
        article = _article(canonical_url=None, headline="A genuinely unique headline no one else has")

        uc.process(article, symbol="AAPL")

        assert embedder.embed_calls == 1
        assert len(writer.writes) == 1

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


class TestNewsIngestedNotifier:
    def test_notifies_for_a_brand_new_article(self):
        repo = FakeRepo()
        notifier = FakeNewsIngestedNotifier()
        uc = ProcessArticleUseCase(
            uow_factory=lambda: FakeUnitOfWork(repo, FakeEmbeddingWriter()),
            dedup_precheck=FakeDedupPrecheck(repo),
            chunker=FakeChunker(),
            embedder=FakeEmbedder(),
            news_ingested_notifier=notifier,
        )
        article = _article(canonical_url="https://example.com/1")

        uc.process(article, symbol="AAPL")

        assert notifier.notified_for == ["AAPL"]

    def test_does_not_notify_on_an_exact_dedup_precheck_match(self):
        # Real bug found live: the poller re-sends the same ~48 articles for
        # a busy symbol every 60s cycle — each is an exact dedup-precheck
        # match (same canonical_url already seen), add_symbol's own ON
        # CONFLICT DO NOTHING is a true no-op, and nothing about the
        # symbol's news actually changed. Notifying on every one of these
        # flooded the Celery queue badly enough to starve a real
        # backfill_symbol task of worker capacity (decision_log_claude.md).
        repo = FakeRepo()
        notifier = FakeNewsIngestedNotifier()
        uc = ProcessArticleUseCase(
            uow_factory=lambda: FakeUnitOfWork(repo, FakeEmbeddingWriter()),
            dedup_precheck=FakeDedupPrecheck(repo),
            chunker=FakeChunker(),
            embedder=FakeEmbedder(),
            news_ingested_notifier=notifier,
        )
        a = _article(canonical_url="https://example.com/1")
        b = _article(canonical_url="https://example.com/1", headline="different headline entirely")

        uc.process(a, symbol="AAPL")
        notifier.notified_for.clear()  # only the repeat matters for this test
        uc.process(b, symbol="MSFT")

        assert notifier.notified_for == []

    def test_does_not_raise_when_no_notifier_is_configured(self, use_case):
        uc, repo, embedder, writer = use_case
        article = _article(canonical_url="https://example.com/1")

        uc.process(article, symbol="AAPL")  # does not raise


class TestInputValidation:
    def test_rejects_blank_headline_before_dedup_or_embedding(self, use_case):
        uc, repo, embedder, writer = use_case
        article = _article(headline="  ", canonical_url="https://example.com/1")

        with pytest.raises(ArticleValidationError):
            uc.process(article, symbol="AAPL")

        assert embedder.embed_calls == 0
        assert len(writer.writes) == 0

    def test_rejects_malformed_symbol_before_dedup_or_embedding(self, use_case):
        uc, repo, embedder, writer = use_case
        article = _article(canonical_url="https://example.com/1")

        with pytest.raises(ArticleValidationError):
            uc.process(article, symbol="not-a-symbol")

        assert embedder.embed_calls == 0
        assert len(writer.writes) == 0


class TestRaceBetweenPrecheckAndTransaction:
    def test_embedding_discarded_not_written_if_duplicate_appears_between_precheck_and_transaction(
        self, use_case
    ):
        # Regression guard for the race the two-phase design must not
        # reintroduce: the read-only pre-check says "new" (nothing registered
        # yet), but by the time the transaction runs, a concurrent writer has
        # already inserted the same content_hash. The already-computed
        # embedding must be discarded, not written against a symbol id the
        # transaction says wasn't newly inserted.
        uc, repo, embedder, writer = use_case
        article = _article(canonical_url=None)

        original_insert = repo.insert_by_content_hash

        def insert_with_concurrent_writer_landing_first(article, content_hash):
            # Simulate another process's insert completing between this
            # request's pre-check and its own transactional insert.
            repo.by_hash[content_hash] = "article-from-concurrent-writer"
            return original_insert(article, content_hash)

        repo.insert_by_content_hash = insert_with_concurrent_writer_landing_first

        article_id = uc.process(article, symbol="AAPL")

        assert article_id == "article-from-concurrent-writer"
        assert embedder.embed_calls == 1  # still computed once (pre-check found nothing)
        assert len(writer.writes) == 0  # but never written, since it wasn't the winning insert
