# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""LlamaStack proxy routes (models, chat, health)."""

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from cuopt_ev_routing_backend.auth import CuoptScope, get_current_user, require_scope
from cuopt_ev_routing_backend.database import get_db
from cuopt_ev_routing_backend.schemas.genai import ChatRequestEnvelope
from cuopt_ev_routing_backend.services import genai as genai_service
from cuopt_ev_routing_backend.services import instance_settings as instance_settings_service

# Router-level scope gate: the cuopt pack model grants ``chat.use`` to the
# ``user`` role and (by wildcard) to ``admin``. Without this gate, the routes
# were authenticated but not authorized — any signed-in caller could exercise
# the LLM proxy regardless of their pack-model permissions. Admin tokens
# bypass scope checks; ``reader``-role tokens (which don't carry chat.use)
# now correctly 403.
router = APIRouter(
    prefix="/api",
    tags=["GenAI"],
    dependencies=[
        Depends(get_current_user),
        Depends(require_scope(CuoptScope.chat_use.value)),
    ],
)


async def _genai_enabled_or_404(db: AsyncSession) -> None:
    """Raise 404 when an admin has disabled GenAI features."""
    row = await instance_settings_service.get_or_create(db)
    if not row.genai_chat_enabled:
        raise HTTPException(status_code=404, detail="GenAI is disabled")


@router.get(
    "/models",
    summary="List available LLM models",
    description=(
        "Fetch `/v1/models` from the upstream LlamaStack and filter the result to "
        "entries whose `custom_metadata.model_type == 'llm'`. Returns 404 when an "
        "admin has disabled the GenAI feature flag."
    ),
    tags=["GenAI"],
    responses={
        200: {"description": "Filtered list of LLM models"},
        401: {"description": "Token missing, invalid, or expired"},
        404: {"description": "GenAI feature flag is disabled"},
        503: {"description": "Upstream LlamaStack is unreachable"},
    },
)
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


@router.post(
    "/genai/chat",
    summary="Send a chat request via LlamaStack",
    description=(
        "Transform the SPA's `chatRequest` envelope (role/content message array) "
        "into a LlamaStack `/v1/responses` payload, forward it, and return the "
        "response in the shape the SPA expects (`chatResponse.text`, "
        "`usageMetadata.{inputTokenCount, outputTokenCount}`). Returns 404 when "
        "an admin has disabled the GenAI feature flag."
    ),
    tags=["GenAI"],
    responses={
        200: {"description": "Chat response and token usage"},
        401: {"description": "Token missing, invalid, or expired"},
        404: {"description": "GenAI feature flag is disabled"},
        422: {"description": "Validation error on the request body"},
        500: {"description": "Upstream LlamaStack request failed"},
    },
)
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


@router.get(
    "/genai/health",
    summary="Probe upstream LlamaStack",
    description=(
        "Probe LlamaStack `/v1/models` as a connectivity check. Returns "
        "`{status: connected, endpoint, defaultModel}` on success or "
        "`{status: unavailable | disconnected}` otherwise. Returns 404 when an "
        "admin has disabled the GenAI feature flag."
    ),
    tags=["GenAI"],
    responses={
        200: {"description": "LlamaStack is reachable"},
        401: {"description": "Token missing, invalid, or expired"},
        404: {"description": "GenAI feature flag is disabled"},
        503: {"description": "Upstream LlamaStack is unreachable"},
    },
)
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
