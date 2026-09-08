import httpx
import pytest

from infrastructure.finnhub_lookup import FinnhubSymbolLookup, InvalidSymbolError, SymbolLookupUnavailableError

SEARCH_RESPONSE = {
    "count": 8,
    "result": [
        {"description": "APPLE INC", "displaySymbol": "AAPL", "symbol": "AAPL", "type": "Common Stock"},
        {"description": "APPLE INC-CDR", "displaySymbol": "AAPL.TO", "symbol": "AAPL.TO", "type": "Canadian DR"},
        {"description": "APPLE INC", "displaySymbol": "AAPL.MX", "symbol": "AAPL.MX", "type": "Common Stock"},
    ],
}

EMPTY_RESPONSE = {"count": 0, "result": []}


def test_validate_accepts_exact_symbol_match(httpx_mock):
    httpx_mock.add_response(json=SEARCH_RESPONSE)
    lookup = FinnhubSymbolLookup(http_client=httpx.Client(), api_key="test-key")

    lookup.validate("AAPL")  # does not raise

    request = httpx_mock.get_requests()[0]
    assert request.url.params["q"] == "AAPL"
    assert request.url.params["token"] == "test-key"


def test_validate_is_case_insensitive(httpx_mock):
    httpx_mock.add_response(json=SEARCH_RESPONSE)
    lookup = FinnhubSymbolLookup(http_client=httpx.Client(), api_key="test-key")

    lookup.validate("aapl")  # does not raise


def test_validate_rejects_cross_exchange_fuzzy_match(httpx_mock):
    # A search for "AAPL.TO" returns AAPL.TO as a legitimate exact result —
    # this test instead confirms a *substring* match on a totally different
    # query doesn't get accepted just because Finnhub's fuzzy search returned
    # something containing similar text.
    httpx_mock.add_response(json=SEARCH_RESPONSE)
    lookup = FinnhubSymbolLookup(http_client=httpx.Client(), api_key="test-key")

    with pytest.raises(InvalidSymbolError):
        lookup.validate("AAPLX")


def test_validate_rejects_unknown_symbol(httpx_mock):
    httpx_mock.add_response(json=EMPTY_RESPONSE)
    lookup = FinnhubSymbolLookup(http_client=httpx.Client(), api_key="test-key")

    with pytest.raises(InvalidSymbolError):
        lookup.validate("ZZZNOTAREALTICKER")


def test_validate_raises_unavailable_error_on_finnhub_5xx(httpx_mock):
    # Real bug found live: a genuine Finnhub 503 propagated as an unhandled
    # httpx.HTTPStatusError, crashing the request with a raw 500 instead of
    # a distinguishable "try again" error (decision_log.md). Distinct from
    # InvalidSymbolError, which means Finnhub answered and the symbol
    # genuinely doesn't exist — this means Finnhub itself didn't answer.
    httpx_mock.add_response(status_code=503)
    lookup = FinnhubSymbolLookup(http_client=httpx.Client(), api_key="test-key")

    with pytest.raises(SymbolLookupUnavailableError):
        lookup.validate("AAPL")


def test_validate_raises_unavailable_error_on_network_failure(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectTimeout("connection timed out"))
    lookup = FinnhubSymbolLookup(http_client=httpx.Client(), api_key="test-key")

    with pytest.raises(SymbolLookupUnavailableError):
        lookup.validate("AAPL")
