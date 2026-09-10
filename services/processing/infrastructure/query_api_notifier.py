from __future__ import annotations

import httpx
import structlog

logger = structlog.get_logger()


class QueryApiNotifier:
    """Tells query-api a symbol just got new news, so it can trigger a
    debounced daily_symbol_features rebuild instead of Stats lagging behind
    the live article count until the next scheduled sweep (user request:
    "if there is new news from polling it should trigger so it match the
    number", decision_log_claude.md). Best-effort: a failure here must never
    break ingestion itself, which already succeeded by the time this runs.
    """

    def __init__(self, http_client: httpx.Client, base_url: str) -> None:
        self._http = http_client
        self._base_url = base_url

    def notify_symbol_news_ingested(self, symbol: str) -> None:
        try:
            response = self._http.post(
                f"{self._base_url}/internal/symbol-news-ingested",
                json={"symbol": symbol},
            )
            response.raise_for_status()
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            logger.warning("query_api_notifier.failed", symbol=symbol, error=str(exc))
