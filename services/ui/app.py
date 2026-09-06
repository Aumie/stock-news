from __future__ import annotations

import os

import streamlit as st

from clients.auth_client import AuthClient
from clients.query_api_client import QueryAPIClient

st.set_page_config(page_title="Stock News Digest", page_icon="📈")

if not st.user.get("is_logged_in", False):
    st.title("Stock News Digest")
    st.write("Sign in with Google to see news for your watchlist.")
    if st.button("Log in with Google"):
        st.login()
    st.stop()

# st.login() verifies the identity with Google directly; the UI then
# exchanges that verified sub for the app's own JWT (§3, §6) — Auth never
# handles the OAuth redirect itself.
AUTH_ADDR = os.environ.get("AUTH_GRPC_ADDR", "localhost:50051")
QUERY_API_URL = os.environ.get("QUERY_API_URL", "http://localhost:8002")

if "jwt" not in st.session_state:
    auth_client = AuthClient(AUTH_ADDR)
    jwt, expires_at_unix = auth_client.exchange_identity(
        google_sub=st.user.sub, email=st.user.email
    )
    st.session_state["jwt"] = jwt
    st.session_state["jwt_expires_at_unix"] = expires_at_unix

st.sidebar.write(f"Signed in as {st.user.email}")
if st.sidebar.button("Log out"):
    st.session_state.pop("jwt", None)
    st.session_state.pop("jwt_expires_at_unix", None)
    st.logout()
    st.stop()

st.title("Stock News Digest")

symbols_input = st.text_input("Symbols (comma-separated)", value="AAPL")
symbols = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]

if question := st.chat_input("Ask about your watchlist's news"):
    st.chat_message("user").write(question)
    query_client = QueryAPIClient(QUERY_API_URL)
    with st.chat_message("assistant"):
        st.write_stream(query_client.query(st.session_state["jwt"], question, symbols))
