# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""LlamaStack proxy routes (models, chat, health)."""

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from cuopt_ev_routing_backend.auth import get_current_user
from cuopt_ev_routing_backend.schemas.genai import ChatRequestEnvelope
from cuopt_ev_routing_backend.services import genai as genai_service

router = APIRouter(prefix="/api", tags=["genai"], dependencies=[Depends(get_current_user)])


@router.get("/models")
async def list_models() -> JSONResponse:
    """List LLM models from LlamaStack."""
    try:
        status_code, data = await genai_service.list_models()
        return JSONResponse(data, status_code=status_code)
    except httpx.HTTPError as exc:
        return JSONResponse(
            {"error": "Failed to fetch models", "message": str(exc)},
            status_code=503,
        )


@router.post("/genai/chat")
async def genai_chat(envelope: ChatRequestEnvelope) -> JSONResponse:
    """Send a chat request through LlamaStack and return the response shape the FE expects."""
    try:
        status_code, data = await genai_service.respond(envelope.chat_request)
        return JSONResponse(data, status_code=status_code)
    except httpx.HTTPError as exc:
        return JSONResponse(
            {"error": "LlamaStack error", "message": str(exc)},
            status_code=500,
        )


@router.get("/genai/health")
async def genai_health() -> JSONResponse:
    """Probe LlamaStack /v1/models as a connectivity check."""
    try:
        status_code, data = await genai_service.health()
        return JSONResponse(data, status_code=status_code)
    except httpx.HTTPError as exc:
        return JSONResponse(
            {"status": "disconnected", "error": str(exc)},
            status_code=503,
        )
