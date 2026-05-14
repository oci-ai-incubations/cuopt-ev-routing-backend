# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Runtime config endpoint — exposes non-secret values to the frontend."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from cuopt_ev_routing_backend.auth import CuoptScope, get_current_user, require_scope
from cuopt_ev_routing_backend.config import settings
from cuopt_ev_routing_backend.database import get_db
from cuopt_ev_routing_backend.services import instance_settings as instance_settings_service

# Router-level scope gate: cuopt pack model grants ``config.read`` to user
# and reader roles. Admin bypasses via wildcard.
router = APIRouter(
    prefix="/api",
    tags=["Configuration"],
    dependencies=[
        Depends(get_current_user),
        Depends(require_scope(CuoptScope.config_read.value)),
    ],
)


@router.get(
    "/config",
    summary="Get runtime SPA configuration",
    description=(
        "Return non-secret runtime values the SPA needs on boot — currently the "
        "Google Maps API key. The admin-managed `instance_settings.google_maps_api_key` "
        "overrides the env-var default when set, so admins can rotate it via "
        "`PATCH /api/admin/config/api-keys` without redeploying."
    ),
    tags=["Configuration"],
    responses={
        200: {"description": "Runtime configuration values"},
        401: {"description": "Token missing, invalid, or expired"},
    },
)
async def runtime_config(db: Annotated[AsyncSession, Depends(get_db)]) -> dict[str, str]:
    """Return runtime configuration values needed by the SPA.

    Admin-managed ``instance_settings.google_maps_api_key`` overrides the
    env-var default when set — admins update it via PATCH /api/admin/config/api-keys
    without redeploying.
    """
    row = await instance_settings_service.get_or_create(db)
    key = row.google_maps_api_key or settings.google_maps_api_key
    return {"googleMapsApiKey": key}
