# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Shared test fixtures."""

import pytest
from fastapi.testclient import TestClient

from cuopt_ev_routing_backend.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=True)
