# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Tests for ``CurrentPrincipal`` construction from user and client tokens.

Exercises the principal-typing logic at the level of ``get_current_principal``
— synthetic Bearer credentials + monkeypatched JWKS opener, no HTTP roundtrip.
"""

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from cuopt_ev_routing_backend.auth import (
    CurrentPrincipal,
    PrincipalType,
    _principal_from_payload,
    get_current_principal,
)
from cuopt_ev_routing_backend.config import settings

from ._auth_helpers import TEST_ISSUER, install_jwks_stub, make_client_token, make_token


def _credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@pytest.fixture
def auth_enabled(monkeypatch):
    monkeypatch.setattr(settings, "auth_require_auth", True)
    monkeypatch.setattr(settings, "auth_trusted_issuers", TEST_ISSUER)
    monkeypatch.setattr(settings, "auth_jwks_cache_ttl", 3600)
    monkeypatch.setattr(settings, "auth_token_audience", "cuopt")
    install_jwks_stub(monkeypatch)


def test_principal_from_payload_user_token_minimal():
    payload = {"sub": "42", "principal_type": "user", "email": "u@example.com", "role": "admin"}
    principal = _principal_from_payload(payload)
    assert principal.principal_type is PrincipalType.user
    assert principal.id == "42"
    assert principal.email == "u@example.com"
    assert principal.role == "admin"
    assert principal.client_id is None
    assert principal.scopes == []


def test_principal_from_payload_client_token_populates_scope_and_client_id():
    payload = {
        "sub": "client:cli_x",
        "principal_type": "client",
        "client_id": "cli_x",
        "scope": "cuopt.solve cuopt.view",
    }
    principal = _principal_from_payload(payload)
    assert principal.principal_type is PrincipalType.client
    assert principal.id == "client:cli_x"
    assert principal.client_id == "cli_x"
    assert principal.scopes == ["cuopt.solve", "cuopt.view"]
    assert principal.email is None
    assert principal.role is None


def test_principal_from_payload_defaults_principal_type_to_user_when_missing():
    """Tokens minted before spec 002 omit principal_type — must read as user."""
    payload = {"sub": "1", "role": "admin"}
    principal = _principal_from_payload(payload)
    assert principal.principal_type is PrincipalType.user


def test_principal_from_payload_rejects_unknown_principal_type():
    payload = {"sub": "1", "principal_type": "service"}
    with pytest.raises(HTTPException) as excinfo:
        _principal_from_payload(payload)
    assert excinfo.value.status_code == 401


def test_principal_from_payload_rejects_empty_principal_type():
    """Explicit empty-string principal_type is malformed, not a missing claim."""
    payload = {"sub": "1", "principal_type": ""}
    with pytest.raises(HTTPException) as excinfo:
        _principal_from_payload(payload)
    assert excinfo.value.status_code == 401


def test_principal_from_payload_empty_scope_yields_empty_list():
    payload = {"sub": "client:x", "principal_type": "client", "scope": ""}
    principal = _principal_from_payload(payload)
    assert principal.scopes == []


def test_principal_from_payload_missing_scope_yields_empty_list():
    payload = {"sub": "client:x", "principal_type": "client"}
    principal = _principal_from_payload(payload)
    assert principal.scopes == []


def test_get_current_principal_user_token(auth_enabled):
    principal = get_current_principal(_credentials(make_token(role="admin")))
    assert principal.principal_type is PrincipalType.user
    assert principal.role == "admin"
    assert principal.id == "42"
    assert principal.scopes == []


def test_get_current_principal_client_token(auth_enabled):
    principal = get_current_principal(
        _credentials(make_client_token(client_id="cli_abc", scope="cuopt.solve cuopt.view"))
    )
    assert principal.principal_type is PrincipalType.client
    assert principal.client_id == "cli_abc"
    assert principal.scopes == ["cuopt.solve", "cuopt.view"]
    assert principal.role is None
    assert principal.email is None


def test_get_current_principal_legacy_user_token_defaults_principal_type(auth_enabled):
    """Tokens minted before spec 002 omit principal_type and must read as user."""
    # make_token without principal_type argument omits the claim entirely.
    principal = get_current_principal(_credentials(make_token(role="reader")))
    assert principal.principal_type is PrincipalType.user
    assert principal.role == "reader"


def test_synthetic_admin_in_dev_mode_is_user_principal(monkeypatch):
    """When auth_require_auth=False the synthetic identity must still be a CurrentPrincipal."""
    monkeypatch.setattr(settings, "auth_require_auth", False)
    principal = get_current_principal(None)
    assert isinstance(principal, CurrentPrincipal)
    assert principal.principal_type is PrincipalType.user
    assert principal.role == "admin"
    assert principal.id == "0"
