from __future__ import annotations

from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.id_token import fetch_id_token

_google_auth_request = GoogleAuthRequest()


def fetch_authorization_header(audience: str) -> str:
    """A Google ID token, as a ready-to-use Authorization header value.

    Cloud Run's own IAM invoker check requires an ID token whose audience is
    the exact target service URL (query-api's own infrastructure/
    cloud_run_id_token.py established this pattern for ui/celery-worker ->
    auth/processing; this is the same mechanism for processing's own
    outbound call to query-api's /internal/symbol-news-ingested, which had
    no auth at all — confirmed live via query-api's request logs, every
    call getting a real 403 "Empty Authorization header value" since the
    IAM invoker binding was added, silently swallowed by QueryApiNotifier's
    best-effort error handling).
    """
    return f"Bearer {fetch_id_token(_google_auth_request, audience)}"
