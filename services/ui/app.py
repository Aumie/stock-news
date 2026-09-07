from __future__ import annotations

import os

import streamlit as st

from clients.auth_client import AuthClient
from views.navigation import build_pages

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

navigation = st.navigation(build_pages())
navigation.run()
