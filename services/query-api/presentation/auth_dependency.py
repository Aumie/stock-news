from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from infrastructure.jwt_verify import InvalidTokenError, verify_token


def require_auth(secret: str):
    def dependency(request: Request) -> str:
        # The app's own JWT lives in X-App-Authorization, not the standard
        # Authorization header — Cloud Run's own IAM invoker check occupies
        # that header with a Google-issued ID token for service-to-service
        # calls (api-spec.md §6: "roles/run.invoker granted only to the UI
        # service's service account; the UI must fetch and attach its own
        # identity token here too"), and a single header can't carry both
        # bearer tokens at once. Found live: the UI's real login flow got a
        # 401 from Cloud Run's own ingress before this code ever ran, since
        # it was still putting the app JWT in the header Cloud Run expects
        # its own ID token in.
        header = request.headers.get("X-App-Authorization")
        if not header or not header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="missing or malformed X-App-Authorization header")

        token = header.removeprefix("Bearer ")
        try:
            claims = verify_token(token, secret=secret)
        except InvalidTokenError as exc:
            raise HTTPException(status_code=401, detail="invalid or expired token") from exc

        return claims.sub

    return Depends(dependency)
