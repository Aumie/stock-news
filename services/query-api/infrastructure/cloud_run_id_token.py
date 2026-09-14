from __future__ import annotations

from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.id_token import fetch_id_token

_google_auth_request = GoogleAuthRequest()


def fetch_authorization_header(audience: str) -> str:
    """A Google ID token, as a ready-to-use Authorization header value.

    Cloud Run's own IAM invoker check requires an ID token whose audience is
    the exact target service URL (ui's clients/query_api_auth.py already
    established this pattern for ui -> auth/query-api; this is the same
    mechanism for query-api/celery-worker -> processing's /articles/ingest,
    which had no auth at all before — that call worked in local dev's
    trusted docker-compose network but got a 403 from Cloud Run's ingress
    once deployed, found live).
    """
    return f"Bearer {fetch_id_token(_google_auth_request, audience)}"
