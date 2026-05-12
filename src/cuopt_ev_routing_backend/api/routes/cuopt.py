# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Proxy routes for the upstream NVIDIA cuopt service."""

from typing import Any

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from cuopt_ev_routing_backend.auth import get_current_user
from cuopt_ev_routing_backend.services import cuopt as cuopt_service

router = APIRouter(prefix="/api", tags=["cuopt"], dependencies=[Depends(get_current_user)])


@router.get("/cuopt/health")
async def cuopt_health() -> Response:
    """Pass through cuopt /cuopt/health (status + raw body)."""
    try:
        status_code, body = await cuopt_service.health()
        return Response(content=body, status_code=status_code, media_type="application/json")
    except httpx.HTTPError as exc:
        return JSONResponse(
            {"status": "disconnected", "error": str(exc)},
            status_code=503,
        )


@router.post("/cuopt/request")
async def cuopt_request(request: Request) -> JSONResponse:
    """Submit an optimization request to upstream cuopt."""
    payload = await request.json()
    try:
        status_code, data = await cuopt_service.submit(payload)
        return JSONResponse(data, status_code=status_code)
    except httpx.HTTPError as exc:
        return JSONResponse(
            {"error": "cuOPT request failed", "message": str(exc)},
            status_code=500,
        )


@router.get("/cuopt/solution/{req_id}")
async def cuopt_solution(req_id: str) -> JSONResponse:
    """Fetch a solution by upstream request id."""
    try:
        status_code, data = await cuopt_service.solution(req_id)
        return JSONResponse(data, status_code=status_code)
    except httpx.HTTPError as exc:
        return JSONResponse(
            {"error": "cuOPT solution failed", "message": str(exc)},
            status_code=500,
        )


__all__: list[Any] = ["router"]
