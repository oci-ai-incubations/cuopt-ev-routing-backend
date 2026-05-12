# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Schemas for the genai/chat endpoint."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ChatRequestEnvelope(BaseModel):
    """Wraps the frontend's chatRequest payload.

    The frontend posts ``{"chatRequest": {...}}``. Inner shape is permissive
    so this layer remains a thin proxy and the upstream LlamaStack contract can
    change without breaking us.
    """

    model_config = ConfigDict(populate_by_name=True)

    chat_request: dict[str, Any] = Field(alias="chatRequest")
