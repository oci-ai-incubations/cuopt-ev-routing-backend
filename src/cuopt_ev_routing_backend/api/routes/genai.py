# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""LlamaStack proxy routes (models, chat, health)."""

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from cuopt_ev_routing_backend.auth import get_current_user
from cuopt_ev_routing_backend.database import get_db
from cuopt_ev_routing_backend.schemas.genai import ChatRequestEnvelope
from cuopt_ev_routing_backend.services import genai as genai_service
from cuopt_ev_routing_backend.services import instance_settings as instance_settings_service

router = APIRouter(prefix="/api", tags=["genai"], dependencies=[Depends(get_current_user)])


async def _genai_enabled_or_404(db: AsyncSession) -> None:
    """Raise 404 when an admin has disabled GenAI features."""
    row = await instance_settings_service.get_or_create(db)
    if not row.genai_chat_enabled:
        raise HTTPException(status_code=404, detail="GenAI is disabled")


@router.get("/models")
async def list_models(db: Annotated[AsyncSession, Depends(get_db)]) -> JSONResponse:
    """List LLM models from LlamaStack."""
    await _genai_enabled_or_404(db)
    try:
        status_code, data = await genai_service.list_models()
        return JSONResponse(data, status_code=status_code)
    except httpx.HTTPError as exc:
        return JSONResponse(
            {"error": "Failed to fetch models", "message": str(exc)},
            status_code=503,
        )


@router.post("/genai/chat")
async def genai_chat(
    envelope: ChatRequestEnvelope,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """Send a chat request through LlamaStack and return the response shape the FE expects."""
    await _genai_enabled_or_404(db)
    try:
        status_code, data = await genai_service.respond(envelope.chat_request)
        return JSONResponse(data, status_code=status_code)
    except httpx.HTTPError as exc:
        return JSONResponse(
            {"error": "LlamaStack error", "message": str(exc)},
            status_code=500,
        )


@router.get("/genai/health")
async def genai_health(db: Annotated[AsyncSession, Depends(get_db)]) -> JSONResponse:
    """Probe LlamaStack /v1/models as a connectivity check."""
    await _genai_enabled_or_404(db)
    try:
        status_code, data = await genai_service.health()
        return JSONResponse(data, status_code=status_code)
    except httpx.HTTPError as exc:
        return JSONResponse(
            {"status": "disconnected", "error": str(exc)},
            status_code=503,
        )
