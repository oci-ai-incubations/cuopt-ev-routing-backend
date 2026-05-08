# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Runtime config endpoint — exposes non-secret values to the frontend."""

from fastapi import APIRouter, Depends

from cuopt_ev_routing_backend.auth import get_current_user
from cuopt_ev_routing_backend.config import settings

router = APIRouter(prefix="/api", tags=["config"], dependencies=[Depends(get_current_user)])


@router.get("/config")
def runtime_config() -> dict[str, str]:
    """Return runtime configuration values needed by the SPA."""
    return {"googleMapsApiKey": settings.google_maps_api_key}
