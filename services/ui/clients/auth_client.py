from __future__ import annotations

import grpc

from auth.v1 import auth_pb2, auth_pb2_grpc


class AuthClient:
    """Calls the Auth service's ExchangeIdentity RPC.

    Cloud deployment fetches its own identity token and attaches it as call
    credentials (api-spec.md, §6) — not implemented here since local
    docker-compose has no such IAM boundary to satisfy; see
    docs/decision_log_claude.md for what's genuinely verified locally.
    """

    def __init__(self, addr: str) -> None:
        self._channel = grpc.insecure_channel(addr)
        self._stub = auth_pb2_grpc.AuthServiceStub(self._channel)

    def exchange_identity(self, google_sub: str, email: str) -> tuple[str, int]:
        request = auth_pb2.ExchangeIdentityRequest(google_sub=google_sub, email=email)
        response = self._stub.ExchangeIdentity(request)
        return response.jwt, response.expires_at_unix
