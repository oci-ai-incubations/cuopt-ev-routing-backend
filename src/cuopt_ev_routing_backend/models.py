# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""SQLAlchemy ORM models for cuopt-ev-routing-backend.

Single-row ``instance_settings`` table holds mutable admin-controlled settings
(API keys + feature flags) that override env-var defaults at runtime.
"""

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Identity, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all cuopt-backend ORM models."""


class InstanceSettings(Base):
    """Mutable instance-level config — exactly one row (id=1).

    Admin-only ``/api/admin/config/*`` endpoints read and write this row. The
    runtime application reads from here first, falling back to env-var
    defaults in :mod:`cuopt_ev_routing_backend.config` when a field is unset.
    """

    __tablename__ = "instance_settings"

    id: Mapped[int] = mapped_column(Integer, Identity(always=True), primary_key=True)

    # API keys (operator-provided; nullable so first-deploy works without any).
    google_maps_api_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    openweathermap_api_key: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Feature flags
    genai_chat_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    weather_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sso_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Audit
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_by: Mapped[str | None] = mapped_column(String(320), nullable=True)
