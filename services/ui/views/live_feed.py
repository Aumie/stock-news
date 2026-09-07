from __future__ import annotations

import os

import streamlit as st

from clients.feed_client import FeedAPIClient

QUERY_API_URL = os.environ.get("QUERY_API_URL", "http://localhost:8002")


def render() -> None:
    st.title("Live Ingestion Feed")

    if st.button("Refresh"):
        st.rerun()

    client = FeedAPIClient(QUERY_API_URL)
    items = client.recent(st.session_state["jwt"])

    if not items:
        st.write("No recent articles for your watchlist yet.")
        return

    for item in items:
        with st.container(border=True):
            st.write(f"**{item['headline']}**")
            st.caption(
                f"{item['source']} · {', '.join(item['symbols'])} · "
                f"published {item['published_at']} · ingested {item['ingested_at']}"
            )
