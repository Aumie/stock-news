from __future__ import annotations

import streamlit as st

from views import live_feed, query_panel, stats, watchlist


def build_pages() -> list[st.Page]:
    # Every view module's entry point is named `render`, so st.Page's default
    # URL-pathname inference (from the callable's own name) collides across
    # all four — explicit url_path is required, not just a nicety (confirmed
    # live: StreamlitAPIException without it, decision_log_claude.md).
    return [
        st.Page(query_panel.render, title="Query", icon="💬", default=True, url_path="query"),
        st.Page(watchlist.render, title="Watchlist", icon="⭐", url_path="watchlist"),
        st.Page(live_feed.render, title="Live Feed", icon="📰", url_path="live-feed"),
        st.Page(stats.render, title="Stats", icon="📊", url_path="stats"),
    ]
