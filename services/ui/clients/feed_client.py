from __future__ import annotations

import httpx

from clients.query_api_auth import build_headers


class FeedAPIClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    def recent(self, jwt: str, before: str | None = None, before_id: str | None = None) -> list[dict]:
        params = {}
        if before is not None:
            params["before"] = before
            params["before_id"] = before_id
        response = httpx.get(
            f"{self._base_url}/feed",
            headers=build_headers(self._base_url, jwt),
            params=params,
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()

    def backfill_more(self, jwt: str) -> dict:
        response = httpx.post(
            f"{self._base_url}/feed/backfill-more",
            headers=build_headers(self._base_url, jwt),
            # Loops over every watched symbol server-side, each doing a real
            # Finnhub fetch + dedup/embed — scales with watchlist size, so a
            # generous timeout (confirmed live: ~5-10s per symbol).
            timeout=180.0,
        )
        response.raise_for_status()
        return response.json()

    def load_older(self, jwt: str, before: str | None = None, before_id: str | None = None) -> dict:
        response = httpx.post(
            f"{self._base_url}/feed/load-older",
            headers=build_headers(self._base_url, jwt),
            json={"before": before, "before_id": before_id},
            # Pages existing Postgres data (cheap) and, if that's empty,
            # enqueues a background Celery task and returns immediately —
            # no longer blocks on Finnhub itself (decision_log.md), so a
            # plain fast timeout is enough.
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()
