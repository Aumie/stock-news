from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class BackfillResult:
    # Only articles_fetched (from Finnhub), not a new-vs-duplicate split —
    # ProcessArticleUseCase.process() doesn't surface whether an article was
    # newly created vs. already-known through its return value (it returns
    # just the article_id, used elsewhere by both /pubsub/push and existing
    # tests), and changing that shared contract for this one caller wasn't
    # worth the ripple (decision_log_claude.md).
    articles_fetched: int
    from_date: date
    to_date: date
    has_more: bool


@dataclass(frozen=True)
class SymbolBackfillResult:
    symbol: str
    result: BackfillResult


@dataclass(frozen=True)
class MultiSymbolBackfillResult:
    per_symbol: list[SymbolBackfillResult]

    @property
    def total_articles_fetched(self) -> int:
        return sum(r.result.articles_fetched for r in self.per_symbol)
