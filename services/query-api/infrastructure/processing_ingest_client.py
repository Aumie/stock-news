from __future__ import annotations

import httpx

from infrastructure.cloud_run_id_token import fetch_authorization_header
from infrastructure.finnhub_news_client import NewsArticle


class ProcessingIngestClient:
    """Calls processing's POST /articles/ingest directly — the same
    dedup/embed pipeline /pubsub/push uses, without the Pub/Sub envelope
    (decision_log.md: this is a synchronous, user-initiated call, not the
    poller's unbounded async arrivals the queue exists to decouple).

    No auth was needed locally (trusted docker-compose network), but Cloud
    Run's own IAM invoker check rejects unauthenticated calls with a 403 —
    found live, every backfill-triggered ingest call failed once processing
    was deployed with its invoker binding locked down. base_url has no
    https:// scheme locally, matching the same discriminator used elsewhere
    in this project's cloud-vs-local client code.
    """

    def __init__(self, http_client: httpx.Client, base_url: str) -> None:
        self._http = http_client
        self._base_url = base_url

    def ingest(self, article: NewsArticle, symbol: str) -> str:
        headers = {}
        if self._base_url.startswith("https://"):
            headers["Authorization"] = fetch_authorization_header(self._base_url)
        response = self._http.post(
            f"{self._base_url}/articles/ingest",
            headers=headers,
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
