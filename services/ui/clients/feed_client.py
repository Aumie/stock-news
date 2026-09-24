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
            # Same query-api cold-start headroom as the other clients
            # (74.66s measured live, stats_client.py/watchlist_client.py) —
            # the Live Feed page can be the first call after a cold
            # instance just as easily as Watchlist.
            timeout=90.0,
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
            # no longer blocks on Finnhub itself (decision_log.md). Still
            # needs query-api cold-start headroom (74.66s measured live)
            # since the fast path assumes a warm instance, not a cold one.
            timeout=90.0,
        )
        response.raise_for_status()
        return response.json()
