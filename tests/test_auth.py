# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Tests for the RS256/JWKS JWT auth dependency."""

import pytest
from fastapi import HTTPException

from cuopt_ev_routing_backend.auth import CurrentUser, _decode_token, get_current_user, require_role
from cuopt_ev_routing_backend.config import settings

from ._auth_helpers import TEST_ISSUER, install_jwks_stub, make_token


@pytest.fixture
def auth_enabled(monkeypatch):
    monkeypatch.setattr(settings, "auth_require_auth", True)
    monkeypatch.setattr(settings, "auth_trusted_issuers", TEST_ISSUER)
    monkeypatch.setattr(settings, "auth_jwks_cache_ttl", 3600)
    monkeypatch.setattr(settings, "auth_token_audience", "cuopt")
    install_jwks_stub(monkeypatch)


def test_decode_valid_token(auth_enabled):
    token = make_token()
    payload = _decode_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == "user"
    assert payload["iss"] == TEST_ISSUER


def test_decode_expired_token_raises_401(auth_enabled):
    token = make_token(exp_offset=-60)
    with pytest.raises(HTTPException) as exc:
        _decode_token(token)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Token expired"


def test_decode_tampered_token_raises_401(auth_enabled, monkeypatch):
    # Sign with a foreign key (regenerate fresh), JWKS still serves the trusted key,
    # so signature verification fails.
    from tests._auth_helpers import _generate_keypair

    _, foreign_private_pem, _ = _generate_keypair()
    token = make_token(private_pem=foreign_private_pem)
    with pytest.raises(HTTPException) as exc:
        _decode_token(token)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid token"


def test_decode_untrusted_issuer_rejected(auth_enabled):
    token = make_token(issuer="https://attacker.example/auth")
    with pytest.raises(HTTPException) as exc:
        _decode_token(token)
    assert exc.value.status_code == 401
    assert "untrusted issuer" in exc.value.detail


def test_decode_missing_kid_rejected(auth_enabled):
    import jwt as pyjwt

    from tests._auth_helpers import TEST_PRIVATE_PEM

    token = pyjwt.encode(
        {"sub": "1", "iss": TEST_ISSUER, "exp": 9999999999},
        TEST_PRIVATE_PEM,
        algorithm="RS256",
    )
    with pytest.raises(HTTPException) as exc:
        _decode_token(token)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Token missing kid header"


def test_decode_unknown_kid_rejected(auth_enabled):
    token = make_token(kid="never-issued-this")
    with pytest.raises(HTTPException) as exc:
        _decode_token(token)
    assert exc.value.status_code == 401
    assert "not in JWKS" in exc.value.detail


def test_protected_route_no_bearer_returns_401(client, auth_enabled):
    resp = client.get("/api/config")
    assert resp.status_code == 401


def test_protected_route_valid_bearer_returns_200(client, auth_enabled):
    token = make_token()
    resp = client.get("/api/config", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert "googleMapsApiKey" in resp.json()


def test_protected_route_expired_bearer_returns_401(client, auth_enabled):
    token = make_token(exp_offset=-60)
    resp = client.get("/api/config", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_protected_route_wrong_scheme_returns_401(client, auth_enabled):
    token = make_token()
    resp = client.get("/api/config", headers={"Authorization": f"Basic {token}"})
    assert resp.status_code == 401


def test_misconfigured_no_trusted_issuers_returns_500(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_require_auth", True)
    monkeypatch.setattr(settings, "auth_trusted_issuers", "")
    token = make_token()
    resp = client.get("/api/config", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 500


def test_auth_disabled_yields_synthetic_admin(client):
    resp = client.get("/api/config")
    assert resp.status_code == 200


def test_get_current_user_dev_mode_returns_synthetic_admin(monkeypatch):
    monkeypatch.setattr(settings, "auth_require_auth", False)
    user = get_current_user(creds=None)
    assert user.role == "admin"
    assert user.email == "dev@local"
    assert user.id == "0"


def test_get_current_user_accepts_uuid_sub(auth_enabled):
    """Federated IdPs (Oracle IDCS, Entra) mint tokens with UUID sub claims —
    ``int(payload["sub"])`` would crash with 500 on these. The dependency
    must accept the value as an opaque string."""
    from fastapi.security import HTTPAuthorizationCredentials

    uuid_sub = "5d8c1a4e-7c2b-4f4f-8b1a-3a4b5c6d7e8f"
    token = make_token(sub=uuid_sub)
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    user = get_current_user(creds=creds)
    assert user.id == uuid_sub


def test_require_role_allows_match():
    user = CurrentUser(id="1", email="a@b.c", name="x", role="admin")
    check = require_role("admin", "user")
    assert check(user=user) is user


def test_require_role_rejects_mismatch():
    user = CurrentUser(id="1", email="a@b.c", name="x", role="reader")
    check = require_role("admin")
    with pytest.raises(HTTPException) as exc:
        check(user=user)
    assert exc.value.status_code == 403
