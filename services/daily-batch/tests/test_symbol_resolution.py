from prices.symbol_resolution import resolve_range, resolve_symbols


def test_resolve_symbols_returns_only_the_requested_symbol_when_given():
    assert resolve_symbols(cli_symbol="AAPL", watched_symbols=["AAPL", "MSFT", "NVDA"]) == ["AAPL"]


def test_resolve_symbols_returns_all_watched_symbols_when_none_given():
    assert resolve_symbols(cli_symbol=None, watched_symbols=["AAPL", "MSFT"]) == ["AAPL", "MSFT"]


def test_resolve_symbols_with_requested_symbol_not_in_watchlist_still_returns_it():
    # On-add trigger fires before the caller can be sure the watchlist read
    # has caught up (real race avoided) — the requested symbol is trusted
    # as-is, not filtered against the current watchlist snapshot.
    assert resolve_symbols(cli_symbol="TSLA", watched_symbols=["AAPL"]) == ["TSLA"]


def test_resolve_range_is_1mo_for_a_single_on_add_symbol():
    # A freshly-added symbol has no price history yet, and the Stats page's
    # 30-day view needs 30 days of it immediately, not built up one day at a
    # time from the next several scheduled sweeps.
    assert resolve_range(cli_symbol="TSLA") == "1mo"


def test_resolve_range_is_5d_for_the_scheduled_sweep():
    # Every other watched symbol already has history from its own on-add
    # pull (or a prior sweep) — the daily sweep only needs to catch up the
    # last few trading days, not re-pull a month for every symbol every day.
    assert resolve_range(cli_symbol=None) == "5d"
