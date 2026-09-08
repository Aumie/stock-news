from __future__ import annotations

import os

import streamlit as st

from clients.watchlist_client import WatchlistAPIClient
from views.formatting import format_timestamp

QUERY_API_URL = os.environ.get("QUERY_API_URL", "http://localhost:8002")


def render() -> None:
    st.title("Watchlist")

    client = WatchlistAPIClient(QUERY_API_URL)
    jwt = st.session_state["jwt"]

    with st.form("add_symbol_form", clear_on_submit=True):
        new_symbol = st.text_input("Add a symbol (e.g. AAPL)")
        submitted = st.form_submit_button("Add")
        if submitted and new_symbol.strip():
            with st.spinner(f"Validating {new_symbol.strip().upper()}..."):
                ok, error = client.add_symbol(jwt, new_symbol.strip())
            if ok:
                st.rerun()
            else:
                # Inline validation error, not a silent failure (§4.1,
                # docs/stock-news-digest-requirements.md's watchlist-management line).
                st.error(f"Couldn't add '{new_symbol.strip().upper()}': {error}")

    entries = client.list_symbols(jwt)
    if not entries:
        st.write("No symbols watched yet — add one above.")
        return

    for entry in entries:
        col1, col2 = st.columns([4, 1])
        label = f"**{entry['symbol']}** — added {format_timestamp(entry['added_at'])}"
        col1.write(label)
        if entry["backfill_pending"]:
            # The news/price backfill runs in a background Celery task, not
            # inline (decision_log.md) — this badge is the honest "still
            # working on it" state, since a freshly-added symbol otherwise
            # just looks empty/incomplete with no explanation (user
            # request). Clears itself on the next natural rerun (switching
            # pages, clicking another button, reloading) once the backfill
            # actually lands — no polling loop needed.
            col1.caption("⏳ Backfilling news in the background — check back in a moment.")
        if col2.button("Remove", key=f"remove_{entry['symbol']}"):
            client.remove_symbol(jwt, entry["symbol"])
            st.rerun()
