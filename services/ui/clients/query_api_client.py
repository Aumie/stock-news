from __future__ import annotations

import httpx

from clients.query_api_auth import build_headers


class QueryAPIClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    def query(self, jwt: str, question: str):
        with httpx.stream(
            "POST",
            f"{self._base_url}/query",
            headers=build_headers(self._base_url, jwt),
            json={"question": question},
            # query-api scales to zero; a real cold start was clocked at
            # 74.66s live (stats_client.py, watchlist_client.py). httpx
            # applies this per-operation (connect/read/write), not as one
            # deadline for the whole stream, so this only widens how long a
            # cold connect or a single slow chunk can take — not how long
            # the LLM's full streamed answer is allowed to run.
            timeout=90.0,
        ) as response:
            response.raise_for_status()
            for chunk in response.iter_text():
                yield chunk
