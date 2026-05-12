# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""HS256 JWT validation for accelerator-pack-auth-service tokens.

Tokens are issued by the shared ``accelerator-pack-auth-service`` and validated
locally with the same ``CUOPT_AUTH_JWT_SECRET``. When ``CUOPT_AUTH_REQUIRE_AUTH``
is false (default), routes that depend on :func:`get_current_user` get a
synthetic admin user instead — useful for local development.
"""

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from cuopt_ev_routing_backend.config import settings


class CurrentUser(BaseModel):
    """User identity attached to an authenticated request."""

    id: int
    email: str
    name: str
    role: str  # admin | user | reader | pending


bearer_scheme = HTTPBearer(auto_error=False)


def _decode_token(token: str) -> dict:
    """Decode an HS256 JWT or raise :class:`HTTPException` (401)."""
    options = {"verify_aud": settings.auth_token_audience is not None}
    try:
        return jwt.decode(
            token,
            settings.auth_jwt_secret,
            algorithms=[settings.auth_jwt_algorithm],
            audience=settings.auth_token_audience,
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
        return CurrentUser(id=0, email="dev@local", name="local-dev", role="admin")

    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing Bearer token")

    if not settings.auth_jwt_secret:
        # Misconfiguration: auth required but no secret — surface as 500, not 401.
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Auth not configured")

    payload = _decode_token(creds.credentials)
    return CurrentUser(
        id=int(payload["sub"]),
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
