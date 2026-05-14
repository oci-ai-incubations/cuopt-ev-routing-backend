# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""RS256 JWT validation for accelerator-pack-auth-service tokens.

Tokens are issued by the shared ``accelerator-pack-auth-service`` and verified
locally against the issuer's published JWKS. ``CUOPT_AUTH_TRUSTED_ISSUERS``
holds a comma-separated allowlist of issuer URLs; the corresponding JWKS is
fetched from ``{issuer}/.well-known/jwks.json`` and cached for
``CUOPT_AUTH_JWKS_CACHE_TTL`` seconds. When ``CUOPT_AUTH_REQUIRE_AUTH`` is
false (default), routes that depend on :func:`get_current_principal` get a
synthetic admin user instead — useful for local development.

The principal model carries both user-typed and client-typed callers (OAuth2
client_credentials). Routes that need to differentiate use
``require_principal_type``; the legacy ``require_role`` helper still works
and naturally rejects clients (which have no role).
"""

from enum import StrEnum
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from cuopt_ev_routing_backend.config import settings
from cuopt_ev_routing_backend.jwks import JwksError, get_signing_key, trusted_issuers


class PrincipalType(StrEnum):
    """Kind of caller carried in a JWT.

    Mirrors ``PrincipalType`` in accelerator-pack-auth-service so the
    cross-service claim shape has one canonical name on both sides.
    """

    user = "user"
    client = "client"


class CuoptScope(StrEnum):
    """Canonical cuopt scope codenames — single source of truth on the BE side.

    Mirrors the scope codenames declared by the auth-service's cuopt pack
    model (``accelerator-pack-auth-service/src/.../pack_models/cuopt.py``).
    There is no programmatic cross-service check today: drift between this
    enum and the auth-service pack model is caught only by integration tests
    and code review. Keep the two in lockstep when adding or renaming scopes.
    """

    cuopt_solve = "cuopt.solve"
    cuopt_view = "cuopt.view"
    chat_use = "chat.use"
    weather_view = "weather.view"
    config_read = "config.read"
    admin_users_manage = "admin.users.manage"
    admin_config_write = "admin.config.write"
    admin_features_toggle = "admin.features.toggle"
    admin_audit_view = "admin.audit.view"


class CurrentPrincipal(BaseModel):
    """Authenticated principal — either a human user or a service account.

    ``id`` is the raw JWT ``sub`` claim. For users it's the auth-service user
    id; for clients it's the ``client:<client_id>`` form (the auth-service
    prefixes ``client:`` so the namespace can't collide with user IDs). The
    cuopt BE doesn't use ``id`` as a DB key, so opaque-string identity is
    fine.

    Tokens that predate the principal_type claim default to ``user`` —
    matches the auth-service's legacy behavior.
    """

    # Defaults to PrincipalType.user so legacy code that constructed
    # ``CurrentUser(id=...)`` without the new claim keeps compiling — the
    # spec defines unspecified principal_type as user.
    principal_type: PrincipalType = PrincipalType.user
    id: str
    email: str | None = None
    name: str | None = None
    role: str | None = None  # admin | user | reader | pending; None for clients
    client_id: str | None = None  # populated only for client tokens
    scopes: list[str] = []  # OAuth2 scope claim, space-split


# Alias kept so existing route signatures and imports continue to compile.
# ``get_current_user`` and ``CurrentUser`` are now thin aliases over the
# principal-typed equivalents — the cuopt routes don't branch on user vs
# client today, and ``role`` / ``email`` / ``name`` still resolve when set.
CurrentUser = CurrentPrincipal


bearer_scheme = HTTPBearer(auto_error=False)


def _decode_token(token: str) -> dict:
    """Decode an RS256 JWT against the issuer's JWKS or raise 401.

    Audience verification is always on (RFC 9068 §4 SHOULD). ``audience`` is
    sourced from ``CUOPT_AUTH_TOKEN_AUDIENCE`` — a comma-separated list of
    allowed audiences, e.g. ``"cuopt,https://cuopt.example.com/api/"``. A
    token's ``aud`` claim matches if it equals any element of the list (PyJWT
    semantics). Tokens with no ``aud`` claim are rejected.
    """
    try:
        unverified_header = jwt.get_unverified_header(token)
        unverified_payload = jwt.decode(token, options={"verify_signature": False})
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from exc

    kid = unverified_header.get("kid")
    if not kid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing kid header")

    issuer = unverified_payload.get("iss")
    if not issuer:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing iss claim")

    try:
        public_key = get_signing_key(issuer, kid)
    except JwksError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    try:
        return jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=settings.auth_token_audience_list,
            issuer=issuer,
            options={"verify_aud": True},
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from exc


def _extract_scopes(payload: dict) -> list[str]:
    """Pull scopes out of a verified JWT, accepting three claim shapes.

    Reads the OAuth2 ``scope`` claim (space-separated string, per RFC 6749 §3.3
    and RFC 9068 — what auth-service and Oracle IDCS emit) first. Falls back
    to ``scp`` (space-separated string — what Microsoft Entra emits for
    delegated permissions) when ``scope`` is absent. Falls back to ``roles``
    (a list, not a string — what Entra emits for application permissions)
    when both ``scope`` and ``scp`` are absent.

    Returning an empty list when no recognized claim is present is correct: it
    forces scope-gated routes to 403 rather than silently allowing a token
    that carries no authorization signal at all.
    """
    scope_claim = payload.get("scope")
    if isinstance(scope_claim, str) and scope_claim:
        return scope_claim.split()
    scp_claim = payload.get("scp")
    if isinstance(scp_claim, str) and scp_claim:
        return scp_claim.split()
    roles_claim = payload.get("roles")
    if isinstance(roles_claim, list):
        return [str(r) for r in roles_claim if r]
    return []


def _principal_from_payload(payload: dict) -> CurrentPrincipal:
    """Translate verified JWT claims into a ``CurrentPrincipal``.

    ``principal_type`` defaults to ``user`` when missing — matches the
    auth-service's legacy behavior for tokens minted before spec 002. Scopes
    are extracted via :func:`_extract_scopes` which understands the
    auth-service / IDCS ``scope`` claim, the Entra delegated-permission
    ``scp`` claim, and the Entra app-roles ``roles`` claim.
    """
    # Explicit ``""`` is malformed and must 401; only a missing claim
    # falls back to the legacy default of ``user``.
    principal_type_raw = payload.get("principal_type", PrincipalType.user.value)
    try:
        principal_type = PrincipalType(principal_type_raw)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown principal_type") from exc
    return CurrentPrincipal(
        principal_type=principal_type,
        id=str(payload["sub"]),
        email=payload.get("email"),
        name=payload.get("name"),
        role=payload.get("role"),
        client_id=payload.get("client_id"),
        scopes=_extract_scopes(payload),
    )


def get_current_principal(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> CurrentPrincipal:
    """Validate the Bearer token and return the authenticated principal.

    When ``CUOPT_AUTH_REQUIRE_AUTH=false`` the dependency emits a synthetic
    admin user without checking the token at all — local-dev convenience.
    """
    if not settings.auth_require_auth:
        # Synthetic admin gets the full cuopt scope set so scope-gated routes
        # (spec 003) keep working under dev mode. The CuoptScope enum is the
        # single source of truth on the BE side; the auth-service pack model
        # is the source on the auth-service side. No programmatic cross-
        # service check — drift is caught by integration tests + review.
        return CurrentPrincipal(
            principal_type=PrincipalType.user,
            id="0",
            email="dev@local",
            name="local-dev",
            role="admin",
            client_id=None,
            scopes=[s.value for s in CuoptScope],
        )

    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing Bearer token")

    if not trusted_issuers():
        # Misconfiguration: auth required but no trusted issuer allowlist.
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Auth not configured")

    payload = _decode_token(creds.credentials)
    return _principal_from_payload(payload)


# Aliased so existing routes that imported ``get_current_user`` keep working.
get_current_user = get_current_principal


def require_role(*allowed: str):
    """Return a dependency that enforces the principal has one of ``allowed`` roles.

    Client principals have no role and are 403'd. Roles are a user concept;
    machine callers should use scope-gated routes (spec 003) or
    ``require_principal_type("client")``.

    The parameter is named ``user`` (not ``principal``) for backward compat:
    callers that built dependencies on top of this name still resolve.
    """

    def _check(
        user: Annotated[CurrentPrincipal, Depends(get_current_principal)],
    ) -> CurrentPrincipal:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user

    return _check


def require_principal_type(expected: PrincipalType):
    """Return a dependency that enforces a specific principal type.

    Use for routes that must be reached only by humans (admin panel UI calls)
    or only by machines (webhook receivers). Mismatched principals return 403.
    """

    def _check(
        principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
    ) -> CurrentPrincipal:
        if principal.principal_type != expected:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"This route requires a {expected.value} principal",
            )
        return principal

    return _check


def require_scope(*required: str):
    """Return a dependency that enforces ALL listed scopes on the bearer token.

    Reads ``principal.scopes`` — already populated from the JWT ``scope``
    claim by ``_principal_from_payload``. Missing scopes are reported in the
    403 detail so the integrator sees exactly which scopes are absent.

    Unlike :func:`require_role`, this dependency works for both user and
    client principals — scope is the per-token authorization signal, role is
    the per-human identity signal. Spec 003.

    Returns the principal so the dep can also be used in a function
    signature when the route needs the caller (e.g.
    ``user: CurrentPrincipal = Depends(require_scope("cuopt.solve"))``).
    Routes that only need the gate use ``dependencies=[...]`` and the return
    value is discarded — mirrors the pattern in :func:`require_role`.
    """

    def _check(
        principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
    ) -> CurrentPrincipal:
        missing = set(required) - set(principal.scopes)
        if missing:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Missing required scopes: {' '.join(sorted(missing))}",
            )
        return principal

    return _check
