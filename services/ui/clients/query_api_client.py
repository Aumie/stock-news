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
            timeout=30.0,
        ) as response:
            response.raise_for_status()
            for chunk in response.iter_text():
                yield chunk
