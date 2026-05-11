# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Shared test fixtures.

The cuopt backend now owns an ``instance_settings`` table (admin-managed
runtime config), so the test suite needs a real database. We point
``CUOPT_DATABASE_URL`` at a session-scoped SQLite tempfile **before**
importing the app — that's the only way the module-level ``engine`` factory
picks it up. The TestClient is used as a context manager so the FastAPI
lifespan runs ``alembic upgrade head`` against the tempfile.

An autouse fixture wipes the single-row ``instance_settings`` table between
tests so each test starts from a clean slate (no per-test app rebuild).
"""

import contextlib
import os
import sqlite3
import tempfile
from pathlib import Path

# IMPORTANT — set env before any cuopt_ev_routing_backend module is imported.
_TEST_DB_PATH = Path(tempfile.gettempdir()) / f"cuopt-test-{os.getpid()}.db"
os.environ.setdefault("CUOPT_DATABASE_TYPE", "sqlite")
os.environ.setdefault("CUOPT_DATABASE_URL", f"sqlite+aiosqlite:///{_TEST_DB_PATH}")

import pytest  # noqa: E402 — must follow env setup above
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    """Session-scoped TestClient. The ``with`` block triggers FastAPI lifespan,
    which runs ``alembic upgrade head`` against the test SQLite tempfile."""
    from cuopt_ev_routing_backend.main import app

    with TestClient(app, raise_server_exceptions=True) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _reset_instance_settings():
    """Delete the singleton ``instance_settings`` row between tests."""
    yield
    if _TEST_DB_PATH.exists():
        con = sqlite3.connect(_TEST_DB_PATH)
        try:
            con.execute("DELETE FROM instance_settings")
            con.commit()
        finally:
            con.close()


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    """Remove the test SQLite tempfile at the end of the session."""
    with contextlib.suppress(FileNotFoundError):
        _TEST_DB_PATH.unlink()
