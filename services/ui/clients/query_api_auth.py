from __future__ import annotations

from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.id_token import fetch_id_token

_google_auth_request = GoogleAuthRequest()


def build_headers(base_url: str, jwt: str) -> dict[str, str]:
    """Auth headers for a Query API call.

    Cloud Run's own IAM invoker check occupies the standard Authorization
    header with a Google-issued ID token for service-to-service calls
    (api-spec.md §6) — a single header can't also carry the app's own JWT,
    so that goes in X-App-Authorization instead, read by query-api's
    auth_dependency.py. Locally (base_url has no https:// scheme), Query API
    has no such IAM boundary, so only the app JWT is sent, unchanged from
    before this fix.
    """
    headers = {"X-App-Authorization": f"Bearer {jwt}"}
    if base_url.startswith("https://"):
        headers["Authorization"] = f"Bearer {fetch_id_token(_google_auth_request, base_url)}"
    return headers
