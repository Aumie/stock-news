from __future__ import annotations

import hashlib
import re
import string

from domain.article import Article

_PUNCTUATION_TABLE = str.maketrans("", "", string.punctuation)


def normalize_headline(headline: str) -> str:
    stripped = headline.translate(_PUNCTUATION_TABLE)
    return re.sub(r"\s+", " ", stripped).strip().lower()


def content_hash(article: Article) -> str:
    minute_bucket = article.published_at.strftime("%Y-%m-%dT%H:%M")
    raw = f"{article.headline}|{article.source}|{minute_bucket}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def fuzzy_key(article: Article) -> str:
    day = article.published_at.strftime("%Y-%m-%d")
    return f"{day}|{normalize_headline(article.headline)}"
