# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Tests for the HS256 JWT auth dependency."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException

from cuopt_ev_routing_backend.auth import CurrentUser, _decode_token, get_current_user, require_role
from cuopt_ev_routing_backend.config import settings

SECRET = "test-secret-very-long-string-for-hs256-tests"


def _make_token(payload: dict, secret: str = SECRET, algorithm: str = "HS256") -> str:
    return jwt.encode(payload, secret, algorithm=algorithm)


def _valid_payload(*, role: str = "user", exp_offset: int = 600) -> dict:
    now = datetime.now(UTC)
    return {
        "sub": "42",
        "email": "u@example.com",
        "name": "Test User",
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=exp_offset)).timestamp()),
    }


@pytest.fixture
def auth_enabled(monkeypatch):
    monkeypatch.setattr(settings, "auth_require_auth", True)
    monkeypatch.setattr(settings, "auth_jwt_secret", SECRET)
    monkeypatch.setattr(settings, "auth_jwt_algorithm", "HS256")
    monkeypatch.setattr(settings, "auth_token_audience", None)


def test_decode_valid_token(auth_enabled):
    token = _make_token(_valid_payload())
    payload = _decode_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == "user"


def test_decode_expired_token_raises_401(auth_enabled):
    token = _make_token(_valid_payload(exp_offset=-60))
    with pytest.raises(HTTPException) as exc:
        _decode_token(token)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Token expired"


def test_decode_tampered_token_raises_401(auth_enabled):
    token = _make_token(_valid_payload(), secret="WRONG_SECRET")
    with pytest.raises(HTTPException) as exc:
        _decode_token(token)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid token"


def test_protected_route_no_bearer_returns_401(client, auth_enabled):
    resp = client.get("/api/config")
    assert resp.status_code == 401


def test_protected_route_valid_bearer_returns_200(client, auth_enabled):
    token = _make_token(_valid_payload())
    resp = client.get("/api/config", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert "googleMapsApiKey" in resp.json()


def test_protected_route_expired_bearer_returns_401(client, auth_enabled):
    token = _make_token(_valid_payload(exp_offset=-60))
    resp = client.get("/api/config", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_protected_route_wrong_scheme_returns_401(client, auth_enabled):
    token = _make_token(_valid_payload())
    resp = client.get("/api/config", headers={"Authorization": f"Basic {token}"})
    assert resp.status_code == 401


def test_misconfigured_no_secret_returns_500(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_require_auth", True)
    monkeypatch.setattr(settings, "auth_jwt_secret", "")
    token = _make_token(_valid_payload())
    resp = client.get("/api/config", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 500


def test_auth_disabled_yields_synthetic_admin(client):
    # default: auth_require_auth=False
    resp = client.get("/api/config")
    assert resp.status_code == 200


def test_get_current_user_dev_mode_returns_synthetic_admin(monkeypatch):
    monkeypatch.setattr(settings, "auth_require_auth", False)
    user = get_current_user(creds=None)
    assert user.role == "admin"
    assert user.email == "dev@local"
    assert user.id == 0


def test_require_role_allows_match():
    user = CurrentUser(id=1, email="a@b.c", name="x", role="admin")
    check = require_role("admin", "user")
    assert check(user=user) is user


def test_require_role_rejects_mismatch():
    user = CurrentUser(id=1, email="a@b.c", name="x", role="reader")
    check = require_role("admin")
    with pytest.raises(HTTPException) as exc:
        check(user=user)
    assert exc.value.status_code == 403
