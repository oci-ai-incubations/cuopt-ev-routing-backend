# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Tests for the ``require_scope`` FastAPI dependency factory (spec 003).

The factory inspects ``principal.scopes`` — the spec-002 field already
populated by ``_principal_from_payload`` from the JWT ``scope`` claim — and
403s when any required scope is missing.
"""

import pytest
from fastapi import HTTPException

from cuopt_ev_routing_backend.auth import CurrentPrincipal, PrincipalType, require_scope


def _principal(
    scopes: list[str], principal_type: PrincipalType = PrincipalType.user
) -> CurrentPrincipal:
    return CurrentPrincipal(
        principal_type=principal_type,
        id="1" if principal_type == PrincipalType.user else "client:cli_x",
        email="u@example.com" if principal_type == PrincipalType.user else None,
        name="U" if principal_type == PrincipalType.user else None,
        role="user" if principal_type == PrincipalType.user else None,
        client_id=None if principal_type == PrincipalType.user else "cli_x",
        scopes=scopes,
    )


def test_require_scope_token_has_required_scope_passes():
    dep = require_scope("cuopt.solve")
    result = dep(_principal(["cuopt.solve", "cuopt.view"]))
    assert result.scopes == ["cuopt.solve", "cuopt.view"]


def test_require_scope_missing_required_scope_403s():
    dep = require_scope("cuopt.solve")
    with pytest.raises(HTTPException) as excinfo:
        dep(_principal(["cuopt.view"]))
    assert excinfo.value.status_code == 403
    assert "cuopt.solve" in excinfo.value.detail


def test_require_scope_multi_scope_only_missing_listed_in_detail():
    """When several scopes are required, the 403 detail lists only the
    actually-missing ones — not the entire required set."""
    dep = require_scope("cuopt.solve", "cuopt.view", "admin.users.manage")
    with pytest.raises(HTTPException) as excinfo:
        dep(_principal(["cuopt.solve", "cuopt.view"]))
    detail = excinfo.value.detail
    assert "admin.users.manage" in detail
    assert "cuopt.solve" not in detail
    assert "cuopt.view" not in detail


def test_require_scope_empty_scopes_on_principal_403s():
    """Tokens minted before spec 003 carry an empty scopes list and must
    fail any scope-gated route — the spec deliberately accepts this break
    rather than silently allowing legacy tokens through scope checks."""
    dep = require_scope("cuopt.solve")
    with pytest.raises(HTTPException) as excinfo:
        dep(_principal([]))
    assert excinfo.value.status_code == 403


def test_require_scope_works_for_client_principal():
    """Service-account tokens carry the scope claim and must pass scope
    checks identically to user tokens. ``require_role`` would 403 these;
    ``require_scope`` is the cross-principal-type check."""
    dep = require_scope("cuopt.solve")
    principal = dep(_principal(["cuopt.solve"], principal_type=PrincipalType.client))
    assert principal.principal_type is PrincipalType.client


def test_require_scope_no_args_always_passes():
    """``require_scope()`` with no args is a degenerate but valid dep — the
    empty required set is trivially satisfied. Keeps the factory composable
    with dynamic scope lists built at module import."""
    dep = require_scope()
    assert dep(_principal([])).scopes == []
