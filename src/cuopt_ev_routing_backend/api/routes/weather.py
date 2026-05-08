# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Weather routes — OpenWeatherMap proxy with mock fallback."""

from fastapi import APIRouter, Depends, HTTPException, Query

from cuopt_ev_routing_backend.auth import get_current_user
from cuopt_ev_routing_backend.services import weather as weather_service

router = APIRouter(
    prefix="/api/weather", tags=["weather"], dependencies=[Depends(get_current_user)]
)


def _validate_coords(lat: float | None, lng: float | None) -> tuple[float, float]:
    if lat is None or lng is None:
        raise HTTPException(status_code=400, detail="lat and lng parameters required")
    return lat, lng


@router.get("/current")
async def current(
    lat: float | None = Query(default=None),
    lng: float | None = Query(default=None),
) -> dict:
    """Current conditions or mock data when no key is configured."""
    lat_, lng_ = _validate_coords(lat, lng)
    return await weather_service.current(lat_, lng_)


@router.get("/forecast")
async def forecast(
    lat: float | None = Query(default=None),
    lng: float | None = Query(default=None),
) -> dict:
    """Forecast or empty-list when no key/error."""
    lat_, lng_ = _validate_coords(lat, lng)
    return await weather_service.forecast(lat_, lng_)


@router.get("/alerts")
async def alerts() -> dict:
    """Always returns ``{"alerts": []}`` — One Call API requires a paid plan."""
    return {"alerts": []}


@router.get("/health")
def weather_health() -> dict:
    """Report whether a real provider key is configured."""
    return weather_service.health()
