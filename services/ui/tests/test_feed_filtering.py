from views.feed_filtering import sort_and_filter_feed

# ingested_at deliberately INVERTED relative to published_at on the first two
# items — a real bug found live: the user wants descending by publish date,
# not ingestion date, and these can diverge (e.g. backfilled old news).
ITEM_OLD = {
    "headline": "old",
    "symbols": ["AAPL"],
    "published_at": "2026-09-01T00:00:00+00:00",
    "ingested_at": "2026-09-20T00:00:00+00:00",
}
ITEM_NEW = {
    "headline": "new",
    "symbols": ["AAPL"],
    "published_at": "2026-09-20T00:00:00+00:00",
    "ingested_at": "2026-09-01T00:00:00+00:00",
}
ITEM_MSFT = {
    "headline": "msft",
    "symbols": ["MSFT"],
    "published_at": "2026-09-10T00:00:00+00:00",
    "ingested_at": "2026-09-10T00:00:00+00:00",
}
ITEM_MULTI = {
    "headline": "multi",
    "symbols": ["AAPL", "MSFT"],
    "published_at": "2026-09-15T00:00:00+00:00",
    "ingested_at": "2026-09-15T00:00:00+00:00",
}


def test_sorts_by_most_recently_published_first():
    result = sort_and_filter_feed([ITEM_OLD, ITEM_NEW], selected_symbols=["AAPL"])

    assert [item["headline"] for item in result] == ["new", "old"]


def test_no_symbols_selected_returns_everything():
    result = sort_and_filter_feed([ITEM_OLD, ITEM_NEW, ITEM_MSFT], selected_symbols=[])

    assert len(result) == 3


def test_filters_to_only_selected_symbols():
    result = sort_and_filter_feed([ITEM_NEW, ITEM_MSFT], selected_symbols=["AAPL"])

    assert [item["headline"] for item in result] == ["new"]


def test_multi_symbol_article_matches_if_any_selected_symbol_is_tagged():
    result = sort_and_filter_feed([ITEM_MULTI, ITEM_MSFT], selected_symbols=["AAPL"])

    assert [item["headline"] for item in result] == ["multi"]
