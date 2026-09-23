from __future__ import annotations

import httpx

from clients.query_api_auth import build_headers


class StatsAPIClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    def get_stats(self, jwt: str) -> dict:
        response = httpx.get(
            f"{self._base_url}/stats",
            headers=build_headers(self._base_url, jwt),
            # 90s — query-api scales to zero (min_instance_count=0) and a
            # cold start loading its SentenceTransformer model can take
            # 10-70+s before the first request even gets served; a real
            # cold-start request was clocked at 74.66s live. Heavy watchlist
            # backfill write load (dozens of sequential ingest calls) can
            # add further headroom on top of that.
            timeout=90.0,
        )
        response.raise_for_status()
        return response.json()
