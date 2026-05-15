# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Tests for ``require_role`` and ``require_principal_type`` factory deps."""

import pytest
from fastapi import HTTPException

from cuopt_ev_routing_backend.auth import (
    CurrentPrincipal,
    PrincipalType,
    require_principal_type,
    require_role,
)


def _user_principal(role: str = "admin") -> CurrentPrincipal:
    return CurrentPrincipal(
        principal_type=PrincipalType.user,
        id="1",
        email="u@example.com",
        name="U",
        role=role,
        client_id=None,
        scopes=[],
    )


def _client_principal(scopes: list[str] | None = None) -> CurrentPrincipal:
    return CurrentPrincipal(
        principal_type=PrincipalType.client,
        id="client:cli_x",
        email=None,
        name=None,
        role=None,
        client_id="cli_x",
        scopes=scopes or [],
    )


def test_require_role_admin_accepts_user_admin():
    dep = require_role("admin")
    principal = dep(_user_principal(role="admin"))
    assert principal.role == "admin"


def test_require_role_admin_rejects_user_with_other_role():
    dep = require_role("admin")
    with pytest.raises(HTTPException) as excinfo:
        dep(_user_principal(role="reader"))
    assert excinfo.value.status_code == 403


def test_require_role_admin_rejects_client_principal():
    """Clients have no role — role-gated routes must 403 them."""
    dep = require_role("admin")
    with pytest.raises(HTTPException) as excinfo:
        dep(_client_principal())
    assert excinfo.value.status_code == 403


def test_require_principal_type_client_accepts_client():
    dep = require_principal_type(PrincipalType.client)
    principal = dep(_client_principal())
    assert principal.principal_type is PrincipalType.client


def test_require_principal_type_client_rejects_user_with_403():
    dep = require_principal_type(PrincipalType.client)
    with pytest.raises(HTTPException) as excinfo:
        dep(_user_principal())
    assert excinfo.value.status_code == 403
    assert "client" in excinfo.value.detail


def test_require_principal_type_user_accepts_user():
    dep = require_principal_type(PrincipalType.user)
    principal = dep(_user_principal())
    assert principal.principal_type is PrincipalType.user


def test_require_principal_type_user_rejects_client_with_403():
    dep = require_principal_type(PrincipalType.user)
    with pytest.raises(HTTPException) as excinfo:
        dep(_client_principal())
    assert excinfo.value.status_code == 403
    assert "user" in excinfo.value.detail
