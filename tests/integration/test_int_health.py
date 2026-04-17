# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Integration smoke tests for health endpoints."""

import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.mark.integration
async def test_healthz(integration_client):
    resp = await integration_client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.integration
async def test_readyz(integration_client):
    resp = await integration_client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
