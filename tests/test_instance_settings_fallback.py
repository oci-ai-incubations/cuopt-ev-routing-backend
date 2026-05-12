# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Tests that runtime routes consult instance_settings before falling back to env."""

from cuopt_ev_routing_backend.config import settings

# /api/config — google_maps_api_key fallback


def test_runtime_config_uses_env_when_instance_unset(client, monkeypatch):
    monkeypatch.setattr(settings, "google_maps_api_key", "env-value")
    resp = client.get("/api/config")
    assert resp.status_code == 200
    assert resp.json()["googleMapsApiKey"] == "env-value"


def test_runtime_config_uses_instance_value_when_set(client, monkeypatch):
    monkeypatch.setattr(settings, "google_maps_api_key", "env-value")
    # Override via admin API
    client.patch(
        "/api/admin/config/api-keys",
        json={"google_maps_api_key": "instance-value"},
    )
    resp = client.get("/api/config")
    assert resp.status_code == 200
    assert resp.json()["googleMapsApiKey"] == "instance-value"


# Feature flag gating


def test_genai_disabled_returns_404(client):
    client.patch("/api/admin/config/features", json={"genai_chat_enabled": False})
    resp = client.get("/api/models")
    assert resp.status_code == 404


def test_weather_disabled_returns_404(client):
    client.patch("/api/admin/config/features", json={"weather_enabled": False})
    resp = client.get("/api/weather/alerts")
    assert resp.status_code == 404
