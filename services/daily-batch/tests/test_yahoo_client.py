from datetime import date

import httpx
import pytest

from prices.yahoo_client import DailyBar, NoDataError, YahooClient, parse_chart_response

SAMPLE_RESPONSE = {
    "chart": {
        "result": [
            {
                "meta": {"symbol": "AAPL"},
                "timestamp": [1789392600, 1789479000],
                "indicators": {
                    "quote": [
                        {
                            "open": [334.79, 330.14],
                            "high": [335.50, 331.78],
                            "low": [331.34, 328.35],
                            "close": [333.08, 331.34],
                            "volume": [39269100, 31748200],
                        }
                    ]
                },
            }
        ],
        "error": None,
    }
}

NO_DATA_RESPONSE = {"chart": {"result": None, "error": {"code": "Not Found", "description": "No data found"}}}


class TestParseChartResponse:
    def test_parses_bars_in_timestamp_order(self):
        bars = parse_chart_response(SAMPLE_RESPONSE)

        assert bars == [
            DailyBar(date=date(2026, 9, 14), open=334.79, high=335.50, low=331.34, close=333.08, volume=39269100),
            DailyBar(date=date(2026, 9, 15), open=330.14, high=331.78, low=328.35, close=331.34, volume=31748200),
        ]

    def test_raises_no_data_error_when_result_is_none(self):
        with pytest.raises(NoDataError):
            parse_chart_response(NO_DATA_RESPONSE)

    def test_skips_bar_with_null_close_mid_session_gap(self):
        response = {
            "chart": {
                "result": [
                    {
                        "meta": {"symbol": "AAPL"},
                        "timestamp": [1789392600, 1789479000],
                        "indicators": {
                            "quote": [
                                {
                                    "open": [334.79, None],
                                    "high": [335.50, None],
                                    "low": [331.34, None],
                                    "close": [333.08, None],
                                    "volume": [39269100, None],
                                }
                            ]
                        },
                    }
                ],
                "error": None,
            }
        }

        bars = parse_chart_response(response)

        assert len(bars) == 1
        assert bars[0].close == 333.08


class TestYahooClient:
    def test_fetch_daily_bars_sends_browser_user_agent_and_daily_range(self, httpx_mock):
        httpx_mock.add_response(json=SAMPLE_RESPONSE)
        client = YahooClient(http_client=httpx.Client())

        bars = client.fetch_daily_bars("AAPL", range_="5d")

        request = httpx_mock.get_requests()[0]
        assert request.url.path == "/v8/finance/chart/AAPL"
        assert request.url.params["interval"] == "1d"
        assert request.url.params["range"] == "5d"
        assert "Mozilla" in request.headers["User-Agent"]
        assert len(bars) == 2

    def test_fetch_daily_bars_raises_no_data_error_on_unknown_symbol(self, httpx_mock):
        httpx_mock.add_response(json=NO_DATA_RESPONSE)
        client = YahooClient(http_client=httpx.Client())

        with pytest.raises(NoDataError):
            client.fetch_daily_bars("NOTASYMBOL", range_="5d")

    def test_fetch_daily_bars_raises_no_data_error_on_http_404(self, httpx_mock):
        # Yahoo returns a bare 404 (not a 200 + NO_DATA_RESPONSE body) for a
        # symbol it's never heard of, confirmed live against the real API.
        httpx_mock.add_response(status_code=404, json={"chart": {"result": None, "error": {"code": "Not Found"}}})
        client = YahooClient(http_client=httpx.Client())

        with pytest.raises(NoDataError):
            client.fetch_daily_bars("ZZZNOTASYMBOL99", range_="5d")
