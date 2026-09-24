from __future__ import annotations

import httpx
import structlog

from infrastructure.cloud_run_id_token import fetch_authorization_header

logger = structlog.get_logger()


class QueryApiNotifier:
    """Tells query-api a symbol just got new news, so it can trigger a
    debounced daily_symbol_features rebuild instead of Stats lagging behind
    the live article count until the next scheduled sweep (user request:
    "if there is new news from polling it should trigger so it match the
    number", decision_log_claude.md). Best-effort: a failure here must never
    break ingestion itself, which already succeeded by the time this runs.

    Real bug found live: this call had no auth at all, so every single
    notification silently failed with a real 403 "Empty Authorization
    header value" once query-api's IAM invoker binding locked it down —
    confirmed via query-api's own request logs, dozens of 403s over hours,
    never surfaced anywhere visible since this is deliberately best-effort.
    symbol_rebuild_debounce stayed permanently empty as a result. Same fix
    as processing_ingest_client.py on the query-api side of this exact
    problem: an ID token whose audience is query-api's own URL, only when
    the URL is a real https:// Cloud Run target (no auth needed locally).
    """

    def __init__(self, http_client: httpx.Client, base_url: str) -> None:
        self._http = http_client
        self._base_url = base_url

    def notify_symbol_news_ingested(self, symbol: str) -> None:
        headers = {}
        if self._base_url.startswith("https://"):
            headers["Authorization"] = fetch_authorization_header(self._base_url)
        try:
            response = self._http.post(
                f"{self._base_url}/internal/symbol-news-ingested",
                headers=headers,
                json={"symbol": symbol},
            )
            response.raise_for_status()
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            logger.warning("query_api_notifier.failed", symbol=symbol, error=str(exc))
