from datetime import datetime, timedelta, timezone

import jwt
import pytest

from infrastructure.jwt_verify import InvalidTokenError, verify_token

SECRET = "test-secret"


def _make_token(sub="user-1", exp=None, secret=SECRET, alg="HS256"):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "iat": now,
        "exp": exp or now + timedelta(hours=24),
    }
    return jwt.encode(payload, secret, algorithm=alg)


def test_verify_valid_token_returns_subject():
    token = _make_token(sub="user-123")
    claims = verify_token(token, secret=SECRET)
    assert claims.sub == "user-123"


def test_rejects_expired_token():
    expired = datetime.now(timezone.utc) - timedelta(hours=1)
    token = _make_token(exp=expired)
    with pytest.raises(InvalidTokenError):
        verify_token(token, secret=SECRET)


def test_rejects_wrong_secret():
    token = _make_token(secret="different-secret")
    with pytest.raises(InvalidTokenError):
        verify_token(token, secret=SECRET)


def test_rejects_malformed_token():
    with pytest.raises(InvalidTokenError):
        verify_token("not-a-jwt", secret=SECRET)


def test_rejects_none_algorithm():
    # regression guard: the classic JWT "alg: none" bypass must be rejected,
    # not silently accepted as valid.
    token = jwt.encode({"sub": "user-1"}, key=None, algorithm="none")
    with pytest.raises(InvalidTokenError):
        verify_token(token, secret=SECRET)
