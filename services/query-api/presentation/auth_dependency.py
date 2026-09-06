from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from infrastructure.jwt_verify import InvalidTokenError, verify_token


def require_auth(secret: str):
    def dependency(request: Request) -> str:
        header = request.headers.get("Authorization")
        if not header or not header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="missing or malformed Authorization header")

        token = header.removeprefix("Bearer ")
        try:
            claims = verify_token(token, secret=secret)
        except InvalidTokenError as exc:
            raise HTTPException(status_code=401, detail="invalid or expired token") from exc

        return claims.sub

    return Depends(dependency)
