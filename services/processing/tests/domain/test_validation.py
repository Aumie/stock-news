from datetime import datetime

import pytest

from domain.article import Article
from domain.validation import ArticleValidationError, validate_article


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


class TestValidText:
    def test_accepts_normal_article(self):
        validate_article(_article(), symbol="AAPL")  # does not raise

    def test_rejects_empty_headline(self):
        with pytest.raises(ArticleValidationError, match="headline"):
            validate_article(_article(headline=""), symbol="AAPL")

    def test_rejects_whitespace_only_headline(self):
        with pytest.raises(ArticleValidationError, match="headline"):
            validate_article(_article(headline="   "), symbol="AAPL")

    def test_rejects_empty_content(self):
        with pytest.raises(ArticleValidationError, match="content"):
            validate_article(_article(content=""), symbol="AAPL")

    def test_rejects_whitespace_only_content(self):
        with pytest.raises(ArticleValidationError, match="content"):
            validate_article(_article(content="\n\t "), symbol="AAPL")


class TestSymbolFormat:
    @pytest.mark.parametrize("symbol", ["AAPL", "A", "GOOGL", "BRK.B", "AAPL.TO"])
    def test_accepts_well_formed_symbols(self, symbol):
        validate_article(_article(), symbol=symbol)  # does not raise

    @pytest.mark.parametrize(
        "symbol",
        ["", "aapl", "TOOLONG1", "AA PL", "AAPL!", "123", "AAPL.TOOLONG"],
    )
    def test_rejects_malformed_symbols(self, symbol):
        with pytest.raises(ArticleValidationError, match="symbol"):
            validate_article(_article(), symbol=symbol)
