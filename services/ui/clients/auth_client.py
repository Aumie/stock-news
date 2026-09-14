from __future__ import annotations

import grpc
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.id_token import fetch_id_token

from auth.v1 import auth_pb2, auth_pb2_grpc


class AuthClient:
    """Calls the Auth service's ExchangeIdentity RPC.

    Locally (docker-compose), addr is a bare host:port with no scheme and
    Auth has no IAM boundary to satisfy, so an insecure channel is used
    unchanged. In the cloud, addr is Auth's real https:// Cloud Run URL —
    the UI fetches its own Google-issued ID token (audience = that URL) via
    Application Default Credentials (the Cloud Run service account's
    metadata server, no key file involved) and attaches it as gRPC call
    credentials over a secure channel, per api-spec.md §6.
    """

    def __init__(self, addr: str) -> None:
        if addr.startswith("https://"):
            target = addr.removeprefix("https://")
            call_creds = grpc.metadata_call_credentials(_GoogleIdTokenPlugin(audience=addr))
            channel_creds = grpc.composite_channel_credentials(
                grpc.ssl_channel_credentials(), call_creds
            )
            self._channel = grpc.secure_channel(target, channel_creds)
        else:
            self._channel = grpc.insecure_channel(addr)
        self._stub = auth_pb2_grpc.AuthServiceStub(self._channel)

    def exchange_identity(self, google_sub: str, email: str) -> tuple[str, int]:
        request = auth_pb2.ExchangeIdentityRequest(google_sub=google_sub, email=email)
        response = self._stub.ExchangeIdentity(request)
        return response.jwt, response.expires_at_unix


class _GoogleIdTokenPlugin(grpc.AuthMetadataPlugin):
    def __init__(self, audience: str) -> None:
        self._audience = audience
        self._request = GoogleAuthRequest()

    def __call__(self, context, callback) -> None:
        # Fetched fresh per call rather than cached — Cloud Run's metadata
        # server call is cheap and this avoids reasoning about the token's
        # own expiry here.
        token = fetch_id_token(self._request, self._audience)
        callback((("authorization", f"Bearer {token}"),), None)
