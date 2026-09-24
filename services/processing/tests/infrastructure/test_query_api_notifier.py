from unittest.mock import patch

import httpx

from infrastructure.query_api_notifier import QueryApiNotifier


class _RecordingTransport(httpx.BaseTransport):
    def __init__(self, response: httpx.Response):
        self.requests: list[httpx.Request] = []
        self._response = response

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        self._response.request = request
        return self._response


def _client(response: httpx.Response) -> tuple[httpx.Client, _RecordingTransport]:
    transport = _RecordingTransport(response)
    return httpx.Client(transport=transport), transport


class TestQueryApiNotifierAuth:
    def test_no_authorization_header_for_a_plain_http_url(self):
        # Local docker-compose target — no real Cloud Run IAM check to
        # satisfy, and no real credentials available to fetch a token with.
        response = httpx.Response(200)
        client, transport = _client(response)
        notifier = QueryApiNotifier(http_client=client, base_url="http://query-api:8002")

        notifier.notify_symbol_news_ingested("AAPL")

        assert len(transport.requests) == 1
        assert "authorization" not in transport.requests[0].headers

    def test_attaches_a_real_id_token_for_an_https_url(self):
        # Real bug found live: this call had none at all, so every request
        # got a real 403 "Empty Authorization header value" from query-api's
        # own Cloud Run IAM invoker check once it was locked down —
        # confirmed via query-api's request logs, symbol_rebuild_debounce
        # staying permanently empty as a result.
        response = httpx.Response(202)
        client, transport = _client(response)
        notifier = QueryApiNotifier(
            http_client=client, base_url="https://query-api-921012126198.us-central1.run.app"
        )

        with patch(
            "infrastructure.query_api_notifier.fetch_authorization_header",
            return_value="Bearer fake-id-token",
        ) as fetch_header:
            notifier.notify_symbol_news_ingested("AAPL")

        fetch_header.assert_called_once_with("https://query-api-921012126198.us-central1.run.app")
        assert transport.requests[0].headers["authorization"] == "Bearer fake-id-token"

    def test_a_403_from_a_missing_token_is_logged_not_raised(self):
        # Best-effort: a failure here must never break ingestion, which
        # already succeeded by the time this notification fires.
        response = httpx.Response(403, text="Empty Authorization header value")
        client, _ = _client(response)
        notifier = QueryApiNotifier(http_client=client, base_url="http://query-api:8002")

        notifier.notify_symbol_news_ingested("AAPL")  # does not raise
