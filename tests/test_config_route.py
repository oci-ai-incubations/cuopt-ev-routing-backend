# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Tests for /api/config (runtime config exposure)."""

from cuopt_ev_routing_backend.config import settings


def test_config_returns_google_maps_key(client, monkeypatch):
    monkeypatch.setattr(settings, "google_maps_api_key", "test-maps-key")
    resp = client.get("/api/config")
    assert resp.status_code == 200
    assert resp.json() == {"googleMapsApiKey": "test-maps-key"}


def test_config_returns_empty_when_unset(client, monkeypatch):
    monkeypatch.setattr(settings, "google_maps_api_key", "")
    resp = client.get("/api/config")
    assert resp.status_code == 200
    assert resp.json() == {"googleMapsApiKey": ""}
