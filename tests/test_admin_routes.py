# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Tests for /api/admin/config* routes."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from cuopt_ev_routing_backend.config import settings

SECRET = "test-secret-very-long-string-for-hs256-tests"


def _make_token(role: str = "admin") -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": "1",
            "email": "a@example.com",
            "name": "A Admin",
            "role": role,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=600)).timestamp()),
        },
        SECRET,
        algorithm="HS256",
    )


@pytest.fixture
def auth_enabled(monkeypatch):
    monkeypatch.setattr(settings, "auth_require_auth", True)
    monkeypatch.setattr(settings, "auth_jwt_secret", SECRET)
    monkeypatch.setattr(settings, "auth_jwt_algorithm", "HS256")
    monkeypatch.setattr(settings, "auth_token_audience", None)


def _auth(headers_role: str = "admin") -> dict[str, str]:
    return {"Authorization": f"Bearer {_make_token(headers_role)}"}


# --- AUTH_REQUIRE_AUTH=false (dev mode) gets synthetic admin --------------


def test_get_config_dev_mode_returns_defaults(client):
    resp = client.get("/api/admin/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["google_maps_api_key"] == ""
    assert body["openweathermap_api_key"] == ""
    assert body["genai_chat_enabled"] is True
    assert body["weather_enabled"] is True
    assert body["sso_enabled"] is False


# --- AUTH_REQUIRE_AUTH=true: 401/403 enforcement ---------------------------


def test_get_config_requires_token(client, auth_enabled):
    resp = client.get("/api/admin/config")
    assert resp.status_code == 401


def test_get_config_non_admin_403(client, auth_enabled):
    resp = client.get("/api/admin/config", headers=_auth("user"))
    assert resp.status_code == 403


def test_get_config_admin_ok(client, auth_enabled):
    resp = client.get("/api/admin/config", headers=_auth("admin"))
    assert resp.status_code == 200


# --- PATCH api-keys --------------------------------------------------------


def test_patch_api_keys_redacts(client, auth_enabled):
    resp = client.patch(
        "/api/admin/config/api-keys",
        json={"google_maps_api_key": "AIza-test-12345"},
        headers=_auth("admin"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["google_maps_api_key"] == "***"
    assert body["openweathermap_api_key"] == ""
    assert body["updated_by"] == "a@example.com"


def test_patch_api_keys_clear_with_empty_string(client, auth_enabled):
    # Set, then clear
    client.patch(
        "/api/admin/config/api-keys",
        json={"google_maps_api_key": "AIza-test"},
        headers=_auth("admin"),
    )
    resp = client.patch(
        "/api/admin/config/api-keys",
        json={"google_maps_api_key": ""},
        headers=_auth("admin"),
    )
    assert resp.status_code == 200
    assert resp.json()["google_maps_api_key"] == ""


def test_patch_api_keys_non_admin_403(client, auth_enabled):
    resp = client.patch(
        "/api/admin/config/api-keys",
        json={"google_maps_api_key": "x"},
        headers=_auth("user"),
    )
    assert resp.status_code == 403


# --- PATCH feature flags ---------------------------------------------------


def test_patch_features_toggle(client, auth_enabled):
    resp = client.patch(
        "/api/admin/config/features",
        json={"genai_chat_enabled": False, "sso_enabled": True},
        headers=_auth("admin"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["genai_chat_enabled"] is False
    assert body["weather_enabled"] is True  # unchanged
    assert body["sso_enabled"] is True


def test_patch_features_partial(client, auth_enabled):
    # Set state
    client.patch(
        "/api/admin/config/features",
        json={"weather_enabled": False},
        headers=_auth("admin"),
    )
    # Patch only one field — other stays
    resp = client.patch(
        "/api/admin/config/features",
        json={"genai_chat_enabled": False},
        headers=_auth("admin"),
    )
    body = resp.json()
    assert body["weather_enabled"] is False  # preserved
    assert body["genai_chat_enabled"] is False


def test_patch_features_non_admin_403(client, auth_enabled):
    resp = client.patch(
        "/api/admin/config/features",
        json={"genai_chat_enabled": False},
        headers=_auth("user"),
    )
    assert resp.status_code == 403
