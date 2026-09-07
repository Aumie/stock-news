from __future__ import annotations

import os

import streamlit as st

from clients.watchlist_client import WatchlistAPIClient

QUERY_API_URL = os.environ.get("QUERY_API_URL", "http://localhost:8002")


def render() -> None:
    st.title("Watchlist")

    client = WatchlistAPIClient(QUERY_API_URL)
    jwt = st.session_state["jwt"]

    with st.form("add_symbol_form", clear_on_submit=True):
        new_symbol = st.text_input("Add a symbol (e.g. AAPL)")
        submitted = st.form_submit_button("Add")
        if submitted and new_symbol.strip():
            ok, error = client.add_symbol(jwt, new_symbol.strip())
            if ok:
                st.rerun()
            else:
                # Inline validation error, not a silent failure (§4.1,
                # docs/stock-news-digest-requirements.md's watchlist-management line).
                st.error(f"'{new_symbol.strip().upper()}' was rejected: {error}")

    entries = client.list_symbols(jwt)
    if not entries:
        st.write("No symbols watched yet — add one above.")
        return

    for entry in entries:
        col1, col2 = st.columns([4, 1])
        col1.write(f"**{entry['symbol']}** — added {entry['added_at']}")
        if col2.button("Remove", key=f"remove_{entry['symbol']}"):
            client.remove_symbol(jwt, entry["symbol"])
            st.rerun()
