# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Weather routes — OpenWeatherMap proxy with mock fallback."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from cuopt_ev_routing_backend.auth import get_current_user
from cuopt_ev_routing_backend.database import get_db
from cuopt_ev_routing_backend.services import instance_settings as instance_settings_service
from cuopt_ev_routing_backend.services import weather as weather_service

router = APIRouter(
    prefix="/api/weather", tags=["weather"], dependencies=[Depends(get_current_user)]
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


@router.get("/current")
async def current(
    db: Annotated[AsyncSession, Depends(get_db)],
    lat: float | None = Query(default=None),
    lng: float | None = Query(default=None),
) -> dict:
    """Current conditions or mock data when no key is configured."""
    await _weather_enabled_or_404(db)
    lat_, lng_ = _validate_coords(lat, lng)
    return await weather_service.current(lat_, lng_)


@router.get("/forecast")
async def forecast(
    db: Annotated[AsyncSession, Depends(get_db)],
    lat: float | None = Query(default=None),
    lng: float | None = Query(default=None),
) -> dict:
    """Forecast or empty-list when no key/error."""
    await _weather_enabled_or_404(db)
    lat_, lng_ = _validate_coords(lat, lng)
    return await weather_service.forecast(lat_, lng_)


@router.get("/alerts")
async def alerts(db: Annotated[AsyncSession, Depends(get_db)]) -> dict:
    """Always returns ``{"alerts": []}`` — One Call API requires a paid plan."""
    await _weather_enabled_or_404(db)
    return {"alerts": []}


@router.get("/health")
async def weather_health(db: Annotated[AsyncSession, Depends(get_db)]) -> dict:
    """Report whether a real provider key is configured."""
    await _weather_enabled_or_404(db)
    return weather_service.health()
