# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Integration test fixtures.

Integration tests run against a live backend instance (and any downstream
services such as cuOpt). Gate them behind ``RUN_INTEGRATION_TESTS=1`` so they
do not run by default.

Quick start:
    RUN_INTEGRATION_TESTS=1 pytest tests/integration/ -v
"""

import os

import httpx
import pytest
import pytest_asyncio

from cuopt_ev_routing_backend.main import app


@pytest.fixture(scope="session", autouse=True)
def skip_if_no_integration() -> None:
    if not os.environ.get("RUN_INTEGRATION_TESTS"):
        pytest.skip("Set RUN_INTEGRATION_TESTS=1 to run integration tests")


@pytest_asyncio.fixture(scope="session")
async def integration_client():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client
