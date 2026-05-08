# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Async HTTP client for the upstream NVIDIA cuopt service."""

import httpx

from cuopt_ev_routing_backend.config import settings

_TIMEOUT = httpx.Timeout(30.0, connect=5.0)


async def health() -> tuple[int, str]:
    """Probe the upstream cuopt /cuopt/health endpoint.

    Returns ``(status_code, body)`` so the caller can pass through the response.
    """
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{settings.cuopt_endpoint}/cuopt/health")
        return resp.status_code, resp.text


async def submit(payload: dict) -> tuple[int, dict]:
    """Submit an optimization request to the upstream cuopt service."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{settings.cuopt_endpoint}/cuopt/request",
            json=payload,
        )
        return resp.status_code, resp.json()


async def solution(req_id: str) -> tuple[int, dict]:
    """Fetch a solution by request id."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{settings.cuopt_endpoint}/cuopt/solution/{req_id}")
        return resp.status_code, resp.json()
