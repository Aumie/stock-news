from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from presentation.auth_dependency import require_auth

SECRET = "test-secret-at-least-32-bytes-long!"


def _make_token(sub="user-1", exp=None):
    now = datetime.now(timezone.utc)
    payload = {"sub": sub, "iat": now, "exp": exp or now + timedelta(hours=24)}
    return jwt.encode(payload, SECRET, algorithm="HS256")


@pytest.fixture
def app():
    app = FastAPI()

    @app.get("/protected")
    def protected(user_id: str = require_auth(secret=SECRET)):
        return {"user_id": user_id}

    return app


def test_valid_token_allows_access(app):
    client = TestClient(app)
    token = _make_token(sub="user-123")

    response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {"user_id": "user-123"}


def test_missing_header_returns_401(app):
    client = TestClient(app)

    response = client.get("/protected")

    assert response.status_code == 401


def test_expired_token_returns_401(app):
    client = TestClient(app)
    expired = datetime.now(timezone.utc) - timedelta(hours=1)
    token = _make_token(exp=expired)

    response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_malformed_header_returns_401(app):
    client = TestClient(app)

    response = client.get("/protected", headers={"Authorization": "NotBearer sometoken"})

    assert response.status_code == 401
