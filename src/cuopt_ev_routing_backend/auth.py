# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""RS256 JWT validation for accelerator-pack-auth-service tokens.

Tokens are issued by the shared ``accelerator-pack-auth-service`` and verified
locally against the issuer's published JWKS. ``CUOPT_AUTH_TRUSTED_ISSUERS``
holds a comma-separated allowlist of issuer URLs; the corresponding JWKS is
fetched from ``{issuer}/.well-known/jwks.json`` and cached for
``CUOPT_AUTH_JWKS_CACHE_TTL`` seconds. When ``CUOPT_AUTH_REQUIRE_AUTH`` is
false (default), routes that depend on :func:`get_current_user` get a
synthetic admin user instead — useful for local development.
"""

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from cuopt_ev_routing_backend.config import settings
from cuopt_ev_routing_backend.jwks import JwksError, get_signing_key, trusted_issuers


class CurrentUser(BaseModel):
    """User identity attached to an authenticated request.

    ``id`` is the JWT ``sub`` claim. It is intentionally typed ``str`` because
    federated IdPs (Oracle IDCS, Microsoft Entra) mint tokens with UUID ``sub``
    values that don't fit ``int``. The cuopt BE doesn't use ``id`` as a DB key
    (this service has no user table), so opaque-string identity is sufficient.
    """

    id: str
    email: str
    name: str
    role: str  # admin | user | reader | pending


bearer_scheme = HTTPBearer(auto_error=False)


def _decode_token(token: str) -> dict:
    """Decode an RS256 JWT against the issuer's JWKS or raise 401."""
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

    options = {"verify_aud": settings.auth_token_audience is not None}
    try:
        return jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=settings.auth_token_audience,
            issuer=issuer,
            options=options,
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from exc


def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> CurrentUser:
    """Validate the request's Bearer token and return the user.

    When ``CUOPT_AUTH_REQUIRE_AUTH=false`` the dependency emits a synthetic
    admin user without checking the token at all — local-dev convenience.
    """
    if not settings.auth_require_auth:
        return CurrentUser(id="0", email="dev@local", name="local-dev", role="admin")

    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing Bearer token")

    if not trusted_issuers():
        # Misconfiguration: auth required but no trusted issuer allowlist.
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Auth not configured")

    payload = _decode_token(creds.credentials)
    return CurrentUser(
        id=str(payload["sub"]),
        email=payload.get("email", ""),
        name=payload.get("name", ""),
        role=payload.get("role", "user"),
    )


def require_role(*allowed: str):
    """Return a dependency that enforces the user has one of ``allowed`` roles."""

    def _check(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user

    return _check
