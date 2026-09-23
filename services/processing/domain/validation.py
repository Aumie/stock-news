from __future__ import annotations

import re

from domain.article import Article

_SYMBOL_PATTERN = re.compile(r"^[A-Z]{1,5}(\.[A-Z]{1,2})?$")


class ArticleValidationError(ValueError):
    """Raised for structurally invalid input, never for a duplicate or an
    unrecognized-but-well-formed symbol — those are handled elsewhere
    (dedup, watchlist validation)."""


def validate_article(article: Article, symbol: str) -> None:
    if not article.headline.strip():
        raise ArticleValidationError("headline must not be empty")
    if not article.content.strip():
        raise ArticleValidationError("content must not be empty")
    if not _SYMBOL_PATTERN.match(symbol):
        raise ArticleValidationError(f"malformed symbol: {symbol!r}")
