# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Helpers for reading/writing the single-row ``instance_settings`` table.

The table is guaranteed to have exactly one row (id=1). Helpers here lazily
insert that row on first read so callers don't have to.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cuopt_ev_routing_backend.models import InstanceSettings


async def get_or_create(db: AsyncSession) -> InstanceSettings:
    """Return the singleton :class:`InstanceSettings`, inserting defaults if absent."""
    row = (await db.execute(select(InstanceSettings).limit(1))).scalar_one_or_none()
    if row is not None:
        return row

    row = InstanceSettings(
        google_maps_api_key=None,
        openweathermap_api_key=None,
        genai_chat_enabled=True,
        weather_enabled=True,
        sso_enabled=False,
        updated_at=datetime.now(UTC),
        updated_by=None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def update(db: AsyncSession, *, updated_by: str | None, **changes) -> InstanceSettings:
    """Apply ``changes`` to the singleton row and commit.

    Only known column names in ``changes`` are honored; everything else is
    ignored (callers should pass already-validated values from a Pydantic body).
    """
    row = await get_or_create(db)

    allowed = {
        "google_maps_api_key",
        "openweathermap_api_key",
        "genai_chat_enabled",
        "weather_enabled",
        "sso_enabled",
    }
    for key, value in changes.items():
        if key in allowed and value is not None:
            setattr(row, key, value)

    row.updated_at = datetime.now(UTC)
    row.updated_by = updated_by
    await db.commit()
    await db.refresh(row)
    return row
