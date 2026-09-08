from __future__ import annotations

import httpx


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
            headers={"Authorization": f"Bearer {jwt}"},
            params=params,
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()

    def backfill_more(self, jwt: str) -> dict:
        response = httpx.post(
            f"{self._base_url}/feed/backfill-more",
            headers={"Authorization": f"Bearer {jwt}"},
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
            headers={"Authorization": f"Bearer {jwt}"},
            json={"before": before, "before_id": before_id},
            # Combines paging existing Postgres data with, if that's
            # exhausted, up to 6 real Finnhub backfill calls (user request:
            # one button instead of two) — the same generous timeout as
            # backfill_more, since the worst case does that many times over.
            timeout=180.0,
        )
        response.raise_for_status()
        return response.json()
