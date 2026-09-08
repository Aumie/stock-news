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
        st.session_state.pop("feed_items_symbols", None)
        st.rerun()

    watchlist_entries = watchlist_client.list_symbols(jwt)
    watched_symbols = sorted(entry["symbol"] for entry in watchlist_entries)
    pending_symbols = sorted(entry["symbol"] for entry in watchlist_entries if entry["backfill_pending"])
    selected_symbols = st.multiselect(
        "Filter by symbol", options=watched_symbols, default=watched_symbols
    )

    if pending_symbols:
        # Explains why a just-added symbol shows no articles yet, rather
        # than looking silently broken — the backfill runs in a background
        # Celery task, not inline (decision_log.md). Clears itself on the
        # next natural rerun once the backfill actually lands.
        st.caption(f"⏳ Still backfilling news for: {', '.join(pending_symbols)}")

    # feed_items accumulates across "Load older news" clicks — a fresh
    # GET /feed only ever returns the first page (most recent), so older
    # pages are appended here rather than replacing what's already shown.
    # Real bug found live: this cache used to only ever clear on an
    # explicit "Refresh" click, so adding a symbol on the Watchlist page and
    # switching back to Live Feed showed stale data — the watchlist itself
    # had changed, but nothing here noticed. Re-fetch whenever the set of
    # watched symbols differs from what feed_items was last fetched for,
    # not just on an explicit click (decision_log.md).
    if st.session_state.get("feed_items_symbols") != set(watched_symbols):
        st.session_state["feed_items"] = feed_client.recent(jwt)
        st.session_state["feed_items_symbols"] = set(watched_symbols)

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
    # existing Postgres data first (cheap), and only reach for Finnhub if
    # paging is empty. The Finnhub backfill itself now runs as a background
    # Celery task rather than blocking this request — Finnhub's company-news
    # endpoint was found live to be unreliable enough (each chunk can take
    # up to its full timeout) that the old synchronous version could block
    # this click for 1-2+ minutes. A "still loading" click enqueues the
    # backfill and returns immediately; click "Load older news" again
    # shortly to check whether it's landed (decision_log.md).
    if st.button("Load older news"):
        cursor = next_page_cursor(sort_and_filter_feed(st.session_state["feed_items"], []))
        before, before_id = cursor if cursor is not None else (None, None)
        result = feed_client.load_older(jwt, before=before, before_id=before_id)
        if not result["items"]:
            if result["backfilling"]:
                st.info("No older news cached yet — fetching more in the background. Try again in a moment.")
            else:
                st.info("No older news found.")
        else:
            st.session_state["feed_items"] = st.session_state["feed_items"] + result["items"]
            st.rerun()
