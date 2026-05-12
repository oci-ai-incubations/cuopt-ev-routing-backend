# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""LlamaStack proxy + chat-format transforms.

Ported from cuopt-ev-routing-frontend/server/app.js (transformToLlamastackFormat
and extractResponseText). The frontend sends a ``chatRequest`` with role/content
arrays; LlamaStack expects ``input`` + ``instructions``.
"""

import httpx

from cuopt_ev_routing_backend.config import settings
from cuopt_ev_routing_backend.services._client import internal_client

_TIMEOUT = httpx.Timeout(60.0, connect=5.0)


def transform_to_llamastack_format(chat_request: dict) -> dict:
    """Transform frontend chatRequest into a LlamaStack /v1/responses payload."""
    raw_messages = chat_request.get("messages") or []
    messages: list[dict] = []
    for m in raw_messages:
        role = (m.get("role") or "").lower()
        content = m.get("content")
        if isinstance(content, list):
            text = "".join(c.get("text", "") for c in content if c.get("type") == "TEXT")
        else:
            text = content or ""
        messages.append({"role": role, "content": text})

    system_msg = next((m for m in messages if m["role"] == "system"), None)
    instructions = (system_msg or {}).get("content") or "You are a helpful assistant"
    input_messages = [m for m in messages if m["role"] != "system"]

    return {
        "input": input_messages,
        "model": chat_request.get("model") or settings.llamastack_model,
        "instructions": instructions,
        "stream": False,
    }


def extract_response_text(data: dict) -> str:
    """Pull text out of a LlamaStack /v1/responses response.

    Falls back through ``output_text`` → ``output[].content[].text`` →
    OpenAI-compat ``choices[0].message.content`` → empty string.
    """
    if data.get("output_text"):
        return data["output_text"]

    output = data.get("output")
    if isinstance(output, list):
        for item in output:
            if item.get("type") == "message" and isinstance(item.get("content"), list):
                parts = "".join(
                    c.get("text", "")
                    for c in item["content"]
                    if c.get("type") in ("output_text", "text")
                )
                if parts:
                    return parts

    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message")
        if isinstance(msg, dict) and msg.get("content"):
            return msg["content"]

    return ""


async def list_models() -> tuple[int, dict]:
    """Fetch /v1/models from LlamaStack and filter to LLM models only."""
    async with internal_client(_TIMEOUT) as client:
        resp = await client.get(f"{settings.llamastack_endpoint}/v1/models")
        if resp.status_code != 200:
            return resp.status_code, {"error": "Failed to fetch models"}
        data = resp.json()
        models = [
            m
            for m in (data.get("data") or [])
            if (m.get("custom_metadata") or {}).get("model_type") == "llm"
        ]
        return 200, {"data": models}


async def respond(chat_request: dict) -> tuple[int, dict]:
    """Send a chat request to LlamaStack and return the parsed response."""
    payload = transform_to_llamastack_format(chat_request)
    async with internal_client(_TIMEOUT) as client:
        resp = await client.post(
            f"{settings.llamastack_endpoint}/v1/responses",
            json=payload,
        )

    if resp.status_code != 200:
        return resp.status_code, {"error": "LlamaStack error", "message": resp.text}

    data = resp.json()
    text = extract_response_text(data)
    usage = data.get("usage") or {}
    return 200, {
        "chatResponse": {"text": text, "choices": None, "finishReason": "stop"},
        "usageMetadata": {
            "inputTokenCount": usage.get("input_tokens", 0),
            "outputTokenCount": usage.get("output_tokens", 0),
        },
    }


async def health() -> tuple[int, dict]:
    """Probe LlamaStack /v1/models as a connectivity check."""
    async with internal_client(_TIMEOUT) as client:
        resp = await client.get(f"{settings.llamastack_endpoint}/v1/models")
    if resp.status_code == 200:
        return 200, {
            "status": "connected",
            "endpoint": settings.llamastack_endpoint,
            "defaultModel": settings.llamastack_model,
        }
    return 503, {"status": "unavailable", "endpoint": settings.llamastack_endpoint}
