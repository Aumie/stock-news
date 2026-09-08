from __future__ import annotations

import httpx

from infrastructure.finnhub_news_client import NewsArticle


class ProcessingIngestClient:
    """Calls processing's POST /articles/ingest directly — the same
    dedup/embed pipeline /pubsub/push uses, without the Pub/Sub envelope
    (decision_log.md: this is a synchronous, user-initiated call, not the
    poller's unbounded async arrivals the queue exists to decouple).
    """

    def __init__(self, http_client: httpx.Client, base_url: str) -> None:
        self._http = http_client
        self._base_url = base_url

    def ingest(self, article: NewsArticle, symbol: str) -> str:
        response = self._http.post(
            f"{self._base_url}/articles/ingest",
            json={
                "source": article.source,
                "headline": article.headline,
                "published_at": article.published_at.isoformat(),
                "content": article.summary,
                "symbol": symbol,
                "canonical_url": article.url,
            },
        )
        response.raise_for_status()
        return response.json()["article_id"]
