# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Weather routes — OpenWeatherMap proxy with mock fallback."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from cuopt_ev_routing_backend.auth import CuoptScope, get_current_user, require_scope
from cuopt_ev_routing_backend.database import get_db
from cuopt_ev_routing_backend.services import instance_settings as instance_settings_service
from cuopt_ev_routing_backend.services import weather as weather_service

# Router-level scope gate: cuopt pack model grants ``weather.view`` to user
# and reader roles. Admin bypasses via wildcard.
router = APIRouter(
    prefix="/api/weather",
    tags=["Weather"],
    dependencies=[
        Depends(get_current_user),
        Depends(require_scope(CuoptScope.weather_view.value)),
    ],
)


async def _weather_enabled_or_404(db: AsyncSession) -> None:
    """Raise 404 when an admin has disabled weather features."""
    row = await instance_settings_service.get_or_create(db)
    if not row.weather_enabled:
        raise HTTPException(status_code=404, detail="Weather is disabled")


def _validate_coords(lat: float | None, lng: float | None) -> tuple[float, float]:
    if lat is None or lng is None:
        raise HTTPException(status_code=400, detail="lat and lng parameters required")
    return lat, lng


@router.get(
    "/current",
    summary="Current weather at coordinates",
    description=(
        "Return current conditions for `(lat, lng)`. Calls the OpenWeatherMap "
        "`/data/2.5/weather` endpoint when `CUOPT_OPENWEATHERMAP_API_KEY` is set, "
        "and falls back to a UK-flavoured synthetic payload otherwise (or on "
        "upstream error)."
    ),
    tags=["Weather"],
    responses={
        200: {"description": "Current weather payload"},
        400: {"description": "Missing `lat` or `lng` query parameter"},
        401: {"description": "Token missing, invalid, or expired"},
        404: {"description": "Weather feature flag is disabled"},
    },
)
async def current(
    db: Annotated[AsyncSession, Depends(get_db)],
    lat: float | None = Query(default=None),
    lng: float | None = Query(default=None),
) -> dict:
    """Current conditions or mock data when no key is configured."""
    await _weather_enabled_or_404(db)
    lat_, lng_ = _validate_coords(lat, lng)
    return await weather_service.current(lat_, lng_)


@router.get(
    "/forecast",
    summary="Weather forecast at coordinates",
    description=(
        "Return the OpenWeatherMap `/data/2.5/forecast` payload for `(lat, lng)`. "
        "Returns `{list: []}` when no provider key is configured or the upstream "
        "call fails."
    ),
    tags=["Weather"],
    responses={
        200: {"description": "Forecast payload"},
        400: {"description": "Missing `lat` or `lng` query parameter"},
        401: {"description": "Token missing, invalid, or expired"},
        404: {"description": "Weather feature flag is disabled"},
    },
)
async def forecast(
    db: Annotated[AsyncSession, Depends(get_db)],
    lat: float | None = Query(default=None),
    lng: float | None = Query(default=None),
) -> dict:
    """Forecast or empty-list when no key/error."""
    await _weather_enabled_or_404(db)
    lat_, lng_ = _validate_coords(lat, lng)
    return await weather_service.forecast(lat_, lng_)


@router.get(
    "/alerts",
    summary="Weather alerts (stub)",
    description=(
        "Always returns `{alerts: []}`. The OpenWeatherMap One Call API which "
        "surfaces real alerts requires a paid plan, so this endpoint exists as "
        "a stable shape for the SPA without consuming a paid quota."
    ),
    tags=["Weather"],
    responses={
        200: {"description": "Empty alerts list"},
        401: {"description": "Token missing, invalid, or expired"},
        404: {"description": "Weather feature flag is disabled"},
    },
)
async def alerts(db: Annotated[AsyncSession, Depends(get_db)]) -> dict:
    """Always returns ``{"alerts": []}`` — One Call API requires a paid plan."""
    await _weather_enabled_or_404(db)
    return {"alerts": []}


@router.get(
    "/health",
    summary="Weather provider configuration probe",
    description=(
        "Report whether a real OpenWeatherMap key is configured. Returns "
        "`{status: configured, provider}` when a key is set, otherwise "
        "`{status: mock_mode, message}` indicating mock data is being served."
    ),
    tags=["Weather"],
    responses={
        200: {"description": "Provider configuration status"},
        401: {"description": "Token missing, invalid, or expired"},
        404: {"description": "Weather feature flag is disabled"},
    },
)
async def weather_health(db: Annotated[AsyncSession, Depends(get_db)]) -> dict:
    """Report whether a real provider key is configured."""
    await _weather_enabled_or_404(db)
    return weather_service.health()
