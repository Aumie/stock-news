from __future__ import annotations

import os

import streamlit as st

from clients.query_api_client import QueryAPIClient

QUERY_API_URL = os.environ.get("QUERY_API_URL", "http://localhost:8002")


def render() -> None:
    st.title("Stock News Digest")

    if question := st.chat_input("Ask about your watchlist's news"):
        st.chat_message("user").write(question)
        query_client = QueryAPIClient(QUERY_API_URL)
        with st.chat_message("assistant"):
            st.write_stream(query_client.query(st.session_state["jwt"], question))
