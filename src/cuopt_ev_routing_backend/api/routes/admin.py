# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Admin-only routes for runtime instance configuration.

These routes back the cuopt FE AdminPanel's "API Keys" and "Feature Flags"
tabs. They read/write :class:`InstanceSettings` (a single-row table), which
overrides env-var defaults in :mod:`cuopt_ev_routing_backend.config` at
runtime. All routes require role ``admin`` via :func:`require_role`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from cuopt_ev_routing_backend.auth import CurrentUser, require_role
from cuopt_ev_routing_backend.database import get_db
from cuopt_ev_routing_backend.schemas.admin import (
    ApiKeysUpdate,
    FeatureFlagsUpdate,
    InstanceConfigResponse,
)
from cuopt_ev_routing_backend.services import instance_settings as instance_settings_service

router = APIRouter(
    prefix="/api/admin",
    tags=["Admin"],
    dependencies=[Depends(require_role("admin"))],
)


def _to_response(row) -> InstanceConfigResponse:  # noqa: ANN001 — InstanceSettings runtime
    """Project an :class:`InstanceSettings` row to its public response shape."""
    return InstanceConfigResponse(
        google_maps_api_key="***" if row.google_maps_api_key else "",
        openweathermap_api_key="***" if row.openweathermap_api_key else "",
        genai_chat_enabled=row.genai_chat_enabled,
        weather_enabled=row.weather_enabled,
        sso_enabled=row.sso_enabled,
        updated_at=row.updated_at,
        updated_by=row.updated_by,
    )


@router.get(
    "/config",
    response_model=InstanceConfigResponse,
    summary="Get instance settings",
    description=(
        "Return the singleton `instance_settings` row that the SPA's AdminPanel "
        'reads. Sensitive values are redacted to `***` when set and `""` when '
        "unset, so the response is safe to render directly in the UI."
    ),
    tags=["Admin"],
    responses={
        200: {"description": "Current instance settings (sensitive values redacted)"},
        401: {"description": "Token missing, invalid, or expired"},
        403: {"description": "Caller is not an admin"},
    },
)
async def get_config(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InstanceConfigResponse:
    """Return the current instance settings (sensitive values redacted)."""
    row = await instance_settings_service.get_or_create(db)
    return _to_response(row)


@router.patch(
    "/config/api-keys",
    response_model=InstanceConfigResponse,
    summary="Update instance API keys",
    description=(
        "Patch the Google Maps and OpenWeatherMap API keys on the singleton "
        "`instance_settings` row. Each field follows three-way semantics: absent "
        "= keep current, empty string = clear, any other value = replace. "
        "`updated_by` is set to the admin's email."
    ),
    tags=["Admin"],
    responses={
        200: {"description": "Updated instance settings (sensitive values redacted)"},
        401: {"description": "Token missing, invalid, or expired"},
        403: {"description": "Caller is not an admin"},
        422: {"description": "Validation error on the request body"},
    },
)
async def patch_api_keys(
    payload: ApiKeysUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_role("admin"))],
) -> InstanceConfigResponse:
    """Update API keys.

    Absent field = keep current; empty string = clear; otherwise replace.
    """
    changes = payload.model_dump(exclude_unset=True)
    row = await instance_settings_service.update(db, updated_by=user.email, **changes)
    return _to_response(row)


@router.patch(
    "/config/features",
    response_model=InstanceConfigResponse,
    summary="Update instance feature flags",
    description=(
        "Toggle the GenAI chat, weather, and SSO feature flags on the singleton "
        "`instance_settings` row. Absent fields are left unchanged. `updated_by` "
        "is set to the admin's email."
    ),
    tags=["Admin"],
    responses={
        200: {"description": "Updated instance settings (sensitive values redacted)"},
        401: {"description": "Token missing, invalid, or expired"},
        403: {"description": "Caller is not an admin"},
        422: {"description": "Validation error on the request body"},
    },
)
async def patch_features(
    payload: FeatureFlagsUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_role("admin"))],
) -> InstanceConfigResponse:
    """Toggle feature flags."""
    changes = payload.model_dump(exclude_unset=True)
    row = await instance_settings_service.update(db, updated_by=user.email, **changes)
    return _to_response(row)
