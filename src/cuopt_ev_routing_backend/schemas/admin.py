# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Pydantic schemas for ``/api/admin/*`` request/response bodies."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InstanceConfigResponse(BaseModel):
    """Public view of :class:`InstanceSettings` — sensitive values redacted."""

    model_config = ConfigDict(extra="ignore")

    google_maps_api_key: str  # "***" when set, "" when unset
    openweathermap_api_key: str  # "***" when set, "" when unset
    genai_chat_enabled: bool
    weather_enabled: bool
    sso_enabled: bool
    updated_at: datetime
    updated_by: str | None = None


class ApiKeysUpdate(BaseModel):
    """PATCH /api/admin/config/api-keys body.

    Each field is optional: absent = keep current; empty string = clear;
    otherwise replace.
    """

    model_config = ConfigDict(extra="forbid")

    google_maps_api_key: str | None = None
    openweathermap_api_key: str | None = None


class FeatureFlagsUpdate(BaseModel):
    """PATCH /api/admin/config/features body."""

    model_config = ConfigDict(extra="forbid")

    genai_chat_enabled: bool | None = None
    weather_enabled: bool | None = None
    sso_enabled: bool | None = None
