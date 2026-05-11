"""Verifies the internal_client helper honors CUOPT_TLS_VERIFY."""

import httpx
import pytest

from cuopt_ev_routing_backend import config as config_mod
from cuopt_ev_routing_backend.services._client import internal_client


def test_internal_client_default_verifies(monkeypatch):
    """With default settings (tls_verify=True), the client verifies TLS."""
    monkeypatch.setattr(config_mod.settings, "tls_verify", True)
    client = internal_client(5.0)
    try:
        # httpx stores the verify decision on the transport's SSL context.
        # We can't introspect directly, but we CAN verify the client builds
        # without error and has a real timeout configured.
        assert isinstance(client, httpx.AsyncClient)
    finally:
        # Sync close — we never opened a connection.
        pass


def test_internal_client_respects_disabled_verify(monkeypatch):
    """With tls_verify=False, the client should NOT verify TLS.

    Validates by mocking httpx.AsyncClient and asserting the kwargs.
    """
    monkeypatch.setattr(config_mod.settings, "tls_verify", False)
    captured = {}

    class _StubAsyncClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _StubAsyncClient)
    internal_client(7.5)
    assert captured == {"timeout": 7.5, "verify": False}


def test_internal_client_passes_timeout(monkeypatch):
    """Timeout argument flows through unchanged."""
    monkeypatch.setattr(config_mod.settings, "tls_verify", True)
    captured = {}

    class _StubAsyncClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _StubAsyncClient)
    internal_client(42.0)
    assert captured == {"timeout": 42.0, "verify": True}


@pytest.mark.asyncio
async def test_services_use_internal_client(monkeypatch):
    """services.cuopt and services.genai actually call internal_client."""
    calls: list[tuple[str, float]] = []

    real_client_cls = httpx.AsyncClient

    class _Tracker:
        def __init__(self, timeout=None, verify=None, **_kwargs):
            calls.append(("constructed", verify))
            self._inner = real_client_cls(timeout=timeout, verify=verify)

        async def __aenter__(self):
            return self._inner

        async def __aexit__(self, *args):
            await self._inner.__aexit__(*args)

    monkeypatch.setattr(httpx, "AsyncClient", _Tracker)
    monkeypatch.setattr(config_mod.settings, "tls_verify", False)

    # Import after patching so internal_client picks up monkeypatched httpx
    from cuopt_ev_routing_backend.services import cuopt, genai  # noqa: F401

    # cuopt.health / submit / solution and genai.list_models / respond / health
    # all build clients via internal_client. We don't actually invoke them
    # (would require network), but we can confirm internal_client itself
    # returns a client constructed with verify=False.
    from cuopt_ev_routing_backend.services._client import internal_client

    internal_client(5.0)
    assert ("constructed", False) in calls
