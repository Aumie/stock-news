from __future__ import annotations

import os

import streamlit as st

from clients.feed_client import FeedAPIClient
from clients.watchlist_client import WatchlistAPIClient
from views.feed_filtering import sort_and_filter_feed
from views.feed_pagination import next_page_cursor
from views.formatting import format_timestamp

QUERY_API_URL = os.environ.get("QUERY_API_URL", "http://localhost:8002")


def render() -> None:
    st.title("Live Ingestion Feed")

    jwt = st.session_state["jwt"]
    feed_client = FeedAPIClient(QUERY_API_URL)
    watchlist_client = WatchlistAPIClient(QUERY_API_URL)

    if st.button("Refresh"):
        st.session_state.pop("feed_items", None)
        st.rerun()

    watched_symbols = sorted(entry["symbol"] for entry in watchlist_client.list_symbols(jwt))
    selected_symbols = st.multiselect(
        "Filter by symbol", options=watched_symbols, default=watched_symbols
    )

    # feed_items accumulates across "Load older news" clicks — a fresh
    # GET /feed only ever returns the first page (most recent), so older
    # pages are appended here rather than replacing what's already shown.
    if "feed_items" not in st.session_state:
        st.session_state["feed_items"] = feed_client.recent(jwt)

    items = sort_and_filter_feed(st.session_state["feed_items"], selected_symbols)

    if not items:
        st.write("No recent articles match this filter.")
    else:
        for item in items:
            with st.container(border=True):
                col1, col2 = st.columns([5, 1])
                col1.write(f"**{item['headline']}**")
                # canonical_url is nullable — a content-hash-deduped article
                # (three-tier dedup, §4.3) can genuinely have no URL, so the
                # button only renders when there's somewhere for it to go.
                if item["canonical_url"]:
                    col2.link_button("Open ↗", item["canonical_url"])
                col1.caption(
                    f"{item['source']} · {', '.join(item['symbols'])} · "
                    f"published {format_timestamp(item['published_at'])} · "
                    f"ingested {format_timestamp(item['ingested_at'])}"
                )

    # One combined action (user request), not two separate buttons: page
    # existing Postgres data first (cheap), and only reach for Finnhub —
    # extending automatically through empty windows up to a bounded number
    # of attempts server-side (FeedLoadOlderService) — once paging is
    # genuinely exhausted. Fixes the real bug where a separate "load 2 more
    # weeks" button fetched real articles that a fixed top-50 feed then had
    # no way to ever display.
    if st.button("Load older news"):
        cursor = next_page_cursor(sort_and_filter_feed(st.session_state["feed_items"], []))
        before, before_id = cursor if cursor is not None else (None, None)
        with st.spinner("Loading older news..."):
            result = feed_client.load_older(jwt, before=before, before_id=before_id)
        if not result["items"]:
            st.info("No older news found." if result["exhausted"] else "No older news found for now — try again shortly.")
        else:
            st.session_state["feed_items"] = st.session_state["feed_items"] + result["items"]
            st.rerun()
