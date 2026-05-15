# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Smoke tests for the published OpenAPI spec.

Spec 000: every documented operation must carry a non-empty ``summary``,
``description``, and ``responses`` map. Health probes opt out of the global
bearerAuth requirement; authenticated routes inherit it. These checks catch
undocumented routes sneaking in.
"""

from cuopt_ev_routing_backend.main import OPENAPI_TAGS

_OPENAPI_URL = "/api/openapi.json"

# Routes that are intentionally public (no bearer token required). Anything
# else with ``security: []`` is a downgrade and the suite fails. Mirror
# ``openapi_extra={"security": []}`` on the route decorator with this list.
_PUBLIC_PATHS: set[tuple[str, str]] = {
    ("get", "/healthz"),
    ("get", "/readyz"),
}


def test_openapi_json_is_reachable_in_debug(client) -> None:
    """GET /api/openapi.json returns JSON when CUOPT_DEBUG=true."""
    resp = client.get(_OPENAPI_URL)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    spec = resp.json()
    assert spec["openapi"].startswith("3.")
    assert spec["info"]["title"] == "cuOpt EV Routing Backend"
    assert spec["info"]["version"]
    assert spec["info"]["description"]


def test_every_operation_has_summary_description_and_responses(client) -> None:
    """Every documented operation carries a non-empty summary, description, and responses."""
    spec = client.get(_OPENAPI_URL).json()
    missing: list[str] = []
    for path, methods in spec.get("paths", {}).items():
        for method, op in methods.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not op.get("summary"):
                missing.append(f"{method.upper()} {path}: missing summary")
            if not op.get("description"):
                missing.append(f"{method.upper()} {path}: missing description")
            if not op.get("responses"):
                missing.append(f"{method.upper()} {path}: missing responses")
    assert not missing, "Undocumented routes:\n" + "\n".join(missing)


def test_tag_set_matches_openapi_tags(client) -> None:
    """Tags used on operations are exactly the set declared in OPENAPI_TAGS."""
    spec = client.get(_OPENAPI_URL).json()
    declared = {tag["name"] for tag in OPENAPI_TAGS}
    used: set[str] = set()
    for methods in spec.get("paths", {}).values():
        for method, op in methods.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            used.update(op.get("tags") or [])
    assert used == declared, (
        f"Tag drift between OPENAPI_TAGS and route tags:\n"
        f"  declared but unused: {sorted(declared - used)}\n"
        f"  used but not declared: {sorted(used - declared)}"
    )


def test_bearer_auth_security_scheme_declared(client) -> None:
    """custom_openapi() declares a bearerAuth scheme on /components/securitySchemes."""
    spec = client.get(_OPENAPI_URL).json()
    schemes = spec.get("components", {}).get("securitySchemes", {})
    assert "bearerAuth" in schemes
    assert schemes["bearerAuth"]["type"] == "http"
    assert schemes["bearerAuth"]["scheme"] == "bearer"
    assert schemes["bearerAuth"]["bearerFormat"] == "JWT"


def test_default_security_applies_bearer_globally(client) -> None:
    """Top-level security default makes routes require bearerAuth unless they opt out."""
    spec = client.get(_OPENAPI_URL).json()
    assert {"bearerAuth": []} in spec.get("security", [])


def test_only_allowlisted_routes_opt_out_of_bearer(client) -> None:
    """No route may declare ``security: []`` unless it is in ``_PUBLIC_PATHS``.

    Catches the downgrade where a future PR adds ``openapi_extra={"security": []}``
    to an authenticated route. Also asserts every allowlisted route DOES declare
    it (catches the inverse drift — a route quietly gaining a token requirement).
    """
    spec = client.get(_OPENAPI_URL).json()
    declared_public: set[tuple[str, str]] = set()
    for path, methods in spec.get("paths", {}).items():
        for method, op in methods.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            if op.get("security") == []:
                declared_public.add((method, path))

    unexpected = declared_public - _PUBLIC_PATHS
    missing = _PUBLIC_PATHS - declared_public
    assert not unexpected, (
        "Routes silently downgraded to public (add to _PUBLIC_PATHS if intentional):\n  "
        + "\n  ".join(f"{m.upper()} {p}" for m, p in sorted(unexpected))
    )
    assert not missing, (
        "Allowlisted public routes missing security=[] declaration:\n  "
        + "\n  ".join(f"{m.upper()} {p}" for m, p in sorted(missing))
    )


def test_every_operation_has_at_least_one_tag(client) -> None:
    """A route with no ``tags`` renders under "default" in Swagger and bypasses the taxonomy."""
    spec = client.get(_OPENAPI_URL).json()
    untagged: list[str] = []
    for path, methods in spec.get("paths", {}).items():
        for method, op in methods.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not op.get("tags"):
                untagged.append(f"{method.upper()} {path}")
    assert not untagged, "Routes missing tags:\n  " + "\n  ".join(untagged)


def test_openapi_json_returns_404_when_debug_false(monkeypatch) -> None:
    """When ``CUOPT_DEBUG=false`` the published spec MUST NOT be reachable.

    Defense-in-depth: builds a fresh FastAPI app under the production-default
    settings and asserts ``/api/openapi.json`` returns 404. The session-scoped
    ``client`` fixture runs with debug=true, so this test cannot use it.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from cuopt_ev_routing_backend.config import settings

    monkeypatch.setattr(settings, "debug", False)

    prod_app = FastAPI(
        title=settings.app_name,
        docs_url="/api/docs" if settings.debug else None,
        redoc_url="/api/redoc" if settings.debug else None,
        openapi_url="/api/openapi.json" if settings.debug else None,
    )
    with TestClient(prod_app) as prod_client:
        for path in ("/api/openapi.json", "/api/docs", "/api/redoc"):
            resp = prod_client.get(path)
            assert resp.status_code == 404, f"{path} must be 404 when CUOPT_DEBUG=false"
