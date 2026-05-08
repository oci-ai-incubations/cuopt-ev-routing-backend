# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""OpenWeatherMap proxy + UK mock-weather generator.

Ported from cuopt-ev-routing-frontend/server/app.js. The mock generator is used
both when no API key is configured and as a fallback on upstream errors. The
randomness here is for synthetic demo data — it is NOT used for any
security-sensitive purpose.
"""

import random  # noqa: S311 — used only for non-cryptographic mock weather data
from datetime import UTC, datetime

import httpx

from cuopt_ev_routing_backend.config import settings

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_OPENWEATHER_BASE = "https://api.openweathermap.org/data/2.5"


def generate_mock_weather(lat: float, lng: float) -> dict:
    """Return a UK-flavoured synthetic weather response for ``(lat, lng)``."""
    hour = datetime.now(UTC).hour
    is_night = hour < 6 or hour > 20

    base_temp = 12 - (lat - 51) * 0.5
    time_adjust = -3 if is_night else 2
    temp = base_temp + time_adjust + (random.random() * 4 - 2)

    has_rain = random.random() < 0.3
    if has_rain:
        condition = {
            "id": 500,
            "main": "Rain",
            "description": "light rain",
            "icon": "10n" if is_night else "10d",
        }
    else:
        condition = {
            "id": 801,
            "main": "Clouds",
            "description": "few clouds",
            "icon": "02n" if is_night else "02d",
        }

    payload = {
        "coord": {"lat": lat, "lon": lng},
        "weather": [condition],
        "main": {
            "temp": round(temp, 1),
            "feels_like": round(temp - 2, 1),
            "humidity": 65 + random.randint(0, 19),
            "pressure": 1013 + random.randint(-10, 9),
        },
        "wind": {
            "speed": 3 + random.random() * 5,
            "gust": 5 + random.random() * 8,
        },
        "clouds": {"all": 40 + random.randint(0, 39)},
        "visibility": 10000,
        "name": "UK Location",
    }
    if has_rain:
        payload["rain"] = {"1h": 0.5 + random.random() * 1.5}
    return payload


async def current(lat: float, lng: float) -> dict:
    """Fetch current weather. Falls back to mock data on missing key or error."""
    if not settings.openweathermap_api_key:
        return generate_mock_weather(lat, lng)

    url = f"{_OPENWEATHER_BASE}/weather"
    params = {"lat": lat, "lon": lng, "appid": settings.openweathermap_api_key, "units": "metric"}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, params=params)
        if resp.status_code != 200:
            return generate_mock_weather(lat, lng)
        return resp.json()
    except httpx.HTTPError:
        return generate_mock_weather(lat, lng)


async def forecast(lat: float, lng: float) -> dict:
    """Fetch forecast or return ``{"list": []}`` if unavailable."""
    if not settings.openweathermap_api_key:
        return {"list": []}

    url = f"{_OPENWEATHER_BASE}/forecast"
    params = {"lat": lat, "lon": lng, "appid": settings.openweathermap_api_key, "units": "metric"}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, params=params)
        if resp.status_code != 200:
            return {"list": []}
        return resp.json()
    except httpx.HTTPError:
        return {"list": []}


def health() -> dict:
    """Report whether a real provider key is configured."""
    if settings.openweathermap_api_key:
        return {"status": "configured", "provider": "OpenWeatherMap"}
    return {"status": "mock_mode", "message": "No API key configured, using mock data"}
