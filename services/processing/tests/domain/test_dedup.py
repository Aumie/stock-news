from datetime import datetime

from domain.article import Article
from domain.dedup import content_hash, fuzzy_key, normalize_headline


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


class TestContentHash:
    def test_same_headline_source_and_minute_hash_equal(self):
        a = _article(published_at=datetime(2026, 9, 4, 14, 30, 0))
        b = _article(published_at=datetime(2026, 9, 4, 14, 30, 45))
        assert content_hash(a) == content_hash(b)

    def test_different_minute_hash_differs(self):
        a = _article(published_at=datetime(2026, 9, 4, 14, 30, 0))
        b = _article(published_at=datetime(2026, 9, 4, 14, 31, 0))
        assert content_hash(a) != content_hash(b)

    def test_different_source_hash_differs(self):
        a = _article(source="finnhub")
        b = _article(source="marketaux")
        assert content_hash(a) != content_hash(b)

    def test_different_headline_hash_differs(self):
        a = _article(headline="Apple unveils new iPhone")
        b = _article(headline="Apple unveils new iPad")
        assert content_hash(a) != content_hash(b)

    def test_hash_is_never_based_on_ingested_at(self):
        # regression guard: ingested_at must never enter the hash, or a
        # same-article re-poll would get a fresh hash every cycle and tier 2
        # would never match anything (see decision_log.md's "Deduplication" section).
        a = _article(ingested_at=datetime(2026, 9, 4, 14, 30, 0))
        b = _article(ingested_at=datetime(2026, 9, 5, 9, 0, 0))
        assert content_hash(a) == content_hash(b)

    def test_content_hash_signature_excludes_symbol(self):
        import inspect

        assert "symbol" not in inspect.signature(content_hash).parameters


class TestNormalizeHeadline:
    def test_case_and_whitespace_insensitive(self):
        assert normalize_headline("  Apple Unveils   New iPhone  ") == normalize_headline(
            "apple unveils new iphone"
        )

    def test_punctuation_ignored(self):
        assert normalize_headline("Apple's new iPhone: a review!") == normalize_headline(
            "Apples new iPhone a review"
        )


class TestFuzzyKey:
    def test_same_day_and_headline_across_sources_match(self):
        # cross-source: tier 3 must match regardless of `source` differing.
        a = _article(source="finnhub", published_at=datetime(2026, 9, 4, 9, 0, 0))
        b = _article(source="marketaux", published_at=datetime(2026, 9, 4, 23, 0, 0))
        assert fuzzy_key(a) == fuzzy_key(b)

    def test_different_day_does_not_match(self):
        a = _article(published_at=datetime(2026, 9, 4, 23, 59, 0))
        b = _article(published_at=datetime(2026, 9, 5, 0, 1, 0))
        assert fuzzy_key(a) != fuzzy_key(b)

    def test_headline_punctuation_and_case_differences_still_match(self):
        a = _article(headline="Apple Unveils New iPhone!")
        b = _article(headline="apple unveils new iphone")
        assert fuzzy_key(a) == fuzzy_key(b)

    def test_key_excludes_source_and_symbol_by_signature(self):
        # regression guard: must never key on source or symbol (decision_log.md,
        # "must never key on source or symbol" — defeats cross-source/cross-symbol
        # dedup by construction).
        import inspect

        sig = inspect.signature(fuzzy_key)
        assert "source" not in sig.parameters
        assert "symbol" not in sig.parameters
