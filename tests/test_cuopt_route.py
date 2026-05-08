# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Tests for /api/cuopt/* proxy routes."""

import httpx
import pytest

from cuopt_ev_routing_backend.config import settings

CUOPT = "https://cuopt-test.example.com"


@pytest.fixture(autouse=True)
def cuopt_endpoint(monkeypatch):
    monkeypatch.setattr(settings, "cuopt_endpoint", CUOPT)


def test_cuopt_health_passthrough(client, httpx_mock):
    httpx_mock.add_response(
        url=f"{CUOPT}/cuopt/health", method="GET", json={"status": "ok"}, status_code=200
    )
    resp = client.get("/api/cuopt/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_cuopt_health_upstream_error(client, httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("boom"), url=f"{CUOPT}/cuopt/health", method="GET")
    resp = client.get("/api/cuopt/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "disconnected"


def test_cuopt_request_proxies(client, httpx_mock):
    httpx_mock.add_response(
        url=f"{CUOPT}/cuopt/request",
        method="POST",
        json={"req_id": "abc"},
        status_code=200,
    )
    resp = client.post("/api/cuopt/request", json={"fleet_data": {}, "task_data": {}})
    assert resp.status_code == 200
    assert resp.json() == {"req_id": "abc"}


def test_cuopt_request_upstream_error(client, httpx_mock):
    httpx_mock.add_exception(
        httpx.ConnectError("boom"), url=f"{CUOPT}/cuopt/request", method="POST"
    )
    resp = client.post("/api/cuopt/request", json={"fleet_data": {}})
    assert resp.status_code == 500
    assert resp.json()["error"] == "cuOPT request failed"


def test_cuopt_solution_proxies(client, httpx_mock):
    httpx_mock.add_response(
        url=f"{CUOPT}/cuopt/solution/req-123",
        method="GET",
        json={"response": {"solver_response": {}}},
        status_code=200,
    )
    resp = client.get("/api/cuopt/solution/req-123")
    assert resp.status_code == 200
    assert "response" in resp.json()


def test_cuopt_solution_upstream_error(client, httpx_mock):
    httpx_mock.add_exception(
        httpx.ConnectError("boom"), url=f"{CUOPT}/cuopt/solution/req-x", method="GET"
    )
    resp = client.get("/api/cuopt/solution/req-x")
    assert resp.status_code == 500


def test_cuopt_health_alt_connected(client, httpx_mock):
    httpx_mock.add_response(
        url=f"{CUOPT}/cuopt/health", method="GET", json={"status": "ok"}, status_code=200
    )
    resp = client.get("/api/cuopt-health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "connected", "endpoint": CUOPT}


def test_cuopt_health_alt_unavailable(client, httpx_mock):
    httpx_mock.add_response(url=f"{CUOPT}/cuopt/health", method="GET", status_code=500, text="bad")
    resp = client.get("/api/cuopt-health")
    assert resp.status_code == 503
    assert resp.json()["status"] == "unavailable"


def test_cuopt_health_alt_disconnected(client, httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("boom"), url=f"{CUOPT}/cuopt/health", method="GET")
    resp = client.get("/api/cuopt-health")
    assert resp.status_code == 503
    assert resp.json()["status"] == "disconnected"
