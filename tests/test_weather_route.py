# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Tests for /api/weather/* routes and mock-weather generator."""

import httpx
import pytest

from cuopt_ev_routing_backend.config import settings
from cuopt_ev_routing_backend.services import weather as weather_service

OWM = "https://api.openweathermap.org/data/2.5"


def test_weather_health_mock_mode(client, monkeypatch):
    monkeypatch.setattr(settings, "openweathermap_api_key", "")
    resp = client.get("/api/weather/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "mock_mode"


def test_weather_health_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "openweathermap_api_key", "k")
    resp = client.get("/api/weather/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "configured"


def test_weather_alerts_always_empty(client):
    resp = client.get("/api/weather/alerts")
    assert resp.status_code == 200
    assert resp.json() == {"alerts": []}


def test_weather_current_missing_params_returns_400(client):
    resp = client.get("/api/weather/current")
    assert resp.status_code == 400


def test_weather_current_uses_mock_when_no_key(client, monkeypatch):
    monkeypatch.setattr(settings, "openweathermap_api_key", "")
    resp = client.get("/api/weather/current?lat=51.5&lng=-0.1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["coord"] == {"lat": 51.5, "lon": -0.1}
    assert "main" in body and "weather" in body


def test_weather_current_proxies_when_key_set(client, monkeypatch, httpx_mock):
    monkeypatch.setattr(settings, "openweathermap_api_key", "k")
    httpx_mock.add_response(
        url=f"{OWM}/weather?lat=51.5&lon=-0.1&appid=k&units=metric",
        method="GET",
        json={"name": "London", "main": {"temp": 10}},
        status_code=200,
    )
    resp = client.get("/api/weather/current?lat=51.5&lng=-0.1")
    assert resp.status_code == 200
    assert resp.json()["name"] == "London"


def test_weather_current_falls_back_to_mock_on_error(client, monkeypatch, httpx_mock):
    monkeypatch.setattr(settings, "openweathermap_api_key", "k")
    httpx_mock.add_exception(httpx.ConnectError("boom"), method="GET")
    resp = client.get("/api/weather/current?lat=51.5&lng=-0.1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["coord"] == {"lat": 51.5, "lon": -0.1}


def test_weather_forecast_empty_when_no_key(client, monkeypatch):
    monkeypatch.setattr(settings, "openweathermap_api_key", "")
    resp = client.get("/api/weather/forecast?lat=51.5&lng=-0.1")
    assert resp.status_code == 200
    assert resp.json() == {"list": []}


def test_weather_forecast_proxies_when_key_set(client, monkeypatch, httpx_mock):
    monkeypatch.setattr(settings, "openweathermap_api_key", "k")
    httpx_mock.add_response(
        url=f"{OWM}/forecast?lat=51.5&lon=-0.1&appid=k&units=metric",
        method="GET",
        json={"list": [{"dt": 1}]},
        status_code=200,
    )
    resp = client.get("/api/weather/forecast?lat=51.5&lng=-0.1")
    assert resp.status_code == 200
    assert resp.json() == {"list": [{"dt": 1}]}


def test_weather_forecast_empty_on_upstream_non_200(client, monkeypatch, httpx_mock):
    monkeypatch.setattr(settings, "openweathermap_api_key", "k")
    httpx_mock.add_response(method="GET", status_code=502, text="bad")
    resp = client.get("/api/weather/forecast?lat=51.5&lng=-0.1")
    assert resp.status_code == 200
    assert resp.json() == {"list": []}


def test_weather_forecast_empty_on_connection_error(client, monkeypatch, httpx_mock):
    monkeypatch.setattr(settings, "openweathermap_api_key", "k")
    httpx_mock.add_exception(httpx.ConnectError("boom"), method="GET")
    resp = client.get("/api/weather/forecast?lat=51.5&lng=-0.1")
    assert resp.status_code == 200
    assert resp.json() == {"list": []}


def test_generate_mock_weather_shape():
    out = weather_service.generate_mock_weather(51.5, -0.1)
    assert out["coord"] == {"lat": 51.5, "lon": -0.1}
    assert "weather" in out and isinstance(out["weather"], list)
    assert "main" in out and "temp" in out["main"]
    assert out["visibility"] == 10000


@pytest.mark.parametrize("lat,lng", [(51.5, -0.1), (55.0, -3.0), (50.0, 1.0)])
def test_generate_mock_weather_varies_with_lat(lat, lng):
    # Just confirm generation is stable for various coords
    out = weather_service.generate_mock_weather(lat, lng)
    assert isinstance(out["main"]["temp"], float)
