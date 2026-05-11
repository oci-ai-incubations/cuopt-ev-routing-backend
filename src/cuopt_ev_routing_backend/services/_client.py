# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Shared httpx client factory.

Centralizes the `verify=` decision for outbound calls. The default is
``CUOPT_TLS_VERIFY=true`` (prod-safe); in clusters where cuopt / llamastack
present self-signed certificates, set ``CUOPT_TLS_VERIFY=false``.

All service modules should use ``internal_client()`` instead of constructing
``httpx.AsyncClient`` directly.
"""

import httpx

from cuopt_ev_routing_backend.config import settings


def internal_client(timeout: float = 30.0) -> httpx.AsyncClient:
    """Return an async httpx client honoring `CUOPT_TLS_VERIFY`."""
    return httpx.AsyncClient(timeout=timeout, verify=settings.tls_verify)
