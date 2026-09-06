from __future__ import annotations

from dataclasses import dataclass

import jwt

ALGORITHM = "HS256"


class InvalidTokenError(Exception):
    pass


@dataclass(frozen=True)
class TokenClaims:
    sub: str


def verify_token(token: str, secret: str) -> TokenClaims:
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc

    sub = payload.get("sub")
    if not sub:
        raise InvalidTokenError("token has no subject claim")

    return TokenClaims(sub=sub)
