# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""HTTP-level scope-gating tests for ``/api/cuopt/*`` (spec 003).

The existing :mod:`test_cuopt_route` runs under ``CUOPT_AUTH_REQUIRE_AUTH=false``
— synthetic-admin gets every cuopt scope, so ``require_scope`` is never
exercised end-to-end through HTTP. A wiring-inversion bug (developer swapped
the scope arg on the two routes) would pass that suite.

This module flips ``settings.auth_require_auth`` to ``True`` per test via
the ``auth_enabled`` fixture (mirroring the pattern in :mod:`test_auth`),
mints RS256 tokens with explicit ``scope`` claims, and asserts the route's
behavior at the HTTP boundary.
"""

from collections.abc import Iterator

import httpx
import pytest

from cuopt_ev_routing_backend.auth import CuoptScope
from cuopt_ev_routing_backend.config import settings

from ._auth_helpers import TEST_ISSUER, install_jwks_stub, make_token

CUOPT = "https://cuopt-test.example.com"


@pytest.fixture
def auth_enabled(monkeypatch) -> Iterator[None]:
    """Flip auth on for a single test and stub JWKS.

    The session-scoped ``client`` fixture is shared with the dev-mode tests,
    so per-test monkeypatching is the only safe way to exercise the real
    auth path without rebuilding the FastAPI app.
    """
    monkeypatch.setattr(settings, "auth_require_auth", True)
    monkeypatch.setattr(settings, "auth_trusted_issuers", TEST_ISSUER)
    monkeypatch.setattr(settings, "auth_jwks_cache_ttl", 3600)
    monkeypatch.setattr(settings, "auth_token_audience", None)
    install_jwks_stub(monkeypatch)
    yield


@pytest.fixture(autouse=True)
def cuopt_endpoint(monkeypatch) -> None:
    """Pin the upstream URL so ``httpx_mock`` can route on it."""
    monkeypatch.setattr(settings, "cuopt_endpoint", CUOPT)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---- POST /api/cuopt/request requires cuopt.solve --------------------------


def test_cuopt_request_with_solve_scope_returns_200(client, auth_enabled, httpx_mock):
    """Token carrying the required scope reaches the upstream and proxies through."""
    httpx_mock.add_response(
        url=f"{CUOPT}/cuopt/request",
        method="POST",
        json={"req_id": "abc"},
        status_code=200,
    )
    token = make_token(scope=CuoptScope.cuopt_solve.value)
    resp = client.post("/api/cuopt/request", json={"fleet_data": {}}, headers=_bearer(token))
    assert resp.status_code == 200
    assert resp.json() == {"req_id": "abc"}


def test_cuopt_request_without_solve_scope_returns_403(client, auth_enabled):
    """Token lacking ``cuopt.solve`` is rejected before reaching the upstream."""
    # Only cuopt.view — the wrong verb for this route.
    token = make_token(scope=CuoptScope.cuopt_view.value)
    resp = client.post("/api/cuopt/request", json={"fleet_data": {}}, headers=_bearer(token))
    assert resp.status_code == 403
    assert CuoptScope.cuopt_solve.value in resp.json()["detail"]


def test_cuopt_request_with_no_scope_claim_returns_403(client, auth_enabled):
    """Legacy / pre-spec-003 tokens (no ``scope`` claim) fail scope gates."""
    token = make_token()  # no scope= argument → claim absent
    resp = client.post("/api/cuopt/request", json={"fleet_data": {}}, headers=_bearer(token))
    assert resp.status_code == 403
    assert CuoptScope.cuopt_solve.value in resp.json()["detail"]


# ---- GET /api/cuopt/solution/{req_id} requires cuopt.view ------------------


def test_cuopt_solution_with_view_scope_returns_200(client, auth_enabled, httpx_mock):
    """Token carrying the required scope reaches the upstream and proxies through."""
    httpx_mock.add_response(
        url=f"{CUOPT}/cuopt/solution/req-123",
        method="GET",
        json={"response": {"solver_response": {}}},
        status_code=200,
    )
    token = make_token(scope=CuoptScope.cuopt_view.value)
    resp = client.get("/api/cuopt/solution/req-123", headers=_bearer(token))
    assert resp.status_code == 200
    assert "response" in resp.json()


def test_cuopt_solution_without_view_scope_returns_403(client, auth_enabled):
    """Token lacking ``cuopt.view`` is rejected before reaching the upstream."""
    # Only cuopt.solve — the wrong verb for this route.
    token = make_token(scope=CuoptScope.cuopt_solve.value)
    resp = client.get("/api/cuopt/solution/req-x", headers=_bearer(token))
    assert resp.status_code == 403
    assert CuoptScope.cuopt_view.value in resp.json()["detail"]


def test_cuopt_solution_with_no_scope_claim_returns_403(client, auth_enabled):
    """Legacy / pre-spec-003 tokens (no ``scope`` claim) fail scope gates."""
    token = make_token()
    resp = client.get("/api/cuopt/solution/req-x", headers=_bearer(token))
    assert resp.status_code == 403
    assert CuoptScope.cuopt_view.value in resp.json()["detail"]


# ---- Wiring-inversion regression pair --------------------------------------
#
# These two tests, taken together, catch the bug-introducer "developer
# swapped the scope arg on the two routes". A swap would let cuopt.view
# unlock POST /request (test 1 below would 200 instead of 403) and
# cuopt.solve unlock GET /solution (test 2 would 200 instead of 403).
# Without this pair, the wiring is verified only at the unit level.


def test_view_only_token_rejected_by_request_route(client, auth_enabled):
    """A token with ONLY cuopt.view must NOT pass POST /api/cuopt/request.

    If this test 200s, someone swapped ``cuopt.solve`` for ``cuopt.view`` on
    the request route in cuopt.py — a classic copy/paste regression.
    """
    token = make_token(scope=CuoptScope.cuopt_view.value)
    resp = client.post("/api/cuopt/request", json={"fleet_data": {}}, headers=_bearer(token))
    assert resp.status_code == 403


def test_solve_only_token_rejected_by_solution_route(client, auth_enabled):
    """A token with ONLY cuopt.solve must NOT pass GET /api/cuopt/solution/{id}.

    If this test 200s, someone swapped ``cuopt.view`` for ``cuopt.solve`` on
    the solution route in cuopt.py — the inverse of the test above.
    """
    token = make_token(scope=CuoptScope.cuopt_solve.value)
    resp = client.get("/api/cuopt/solution/req-x", headers=_bearer(token))
    assert resp.status_code == 403


# ---- 401 still wins over 403 -----------------------------------------------


def test_cuopt_request_no_bearer_returns_401(client, auth_enabled):
    """Missing token yields 401, not 403 — auth precedes authz."""
    resp = client.post("/api/cuopt/request", json={"fleet_data": {}})
    assert resp.status_code == 401


def test_cuopt_solution_no_bearer_returns_401(client, auth_enabled):
    """Missing token yields 401, not 403 — auth precedes authz."""
    resp = client.get("/api/cuopt/solution/req-x")
    assert resp.status_code == 401


# ---- Upstream is mocked: solve-scope happy path doesn't hit the network ----


def test_cuopt_request_solve_scope_propagates_upstream_error(client, auth_enabled, httpx_mock):
    """Once the scope check passes, the route still surfaces upstream failures."""
    httpx_mock.add_exception(
        httpx.ConnectError("boom"), url=f"{CUOPT}/cuopt/request", method="POST"
    )
    token = make_token(scope=CuoptScope.cuopt_solve.value)
    resp = client.post("/api/cuopt/request", json={"fleet_data": {}}, headers=_bearer(token))
    assert resp.status_code == 500
    assert resp.json()["error"] == "cuOPT request failed"
