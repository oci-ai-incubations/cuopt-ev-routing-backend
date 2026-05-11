"""Initial instance_settings table.

Revision ID: 001
Revises:
Create Date: 2026-05-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "instance_settings",
        sa.Column("id", sa.Integer, sa.Identity(always=True), primary_key=True),
        sa.Column("google_maps_api_key", sa.String(512), nullable=True),
        sa.Column("openweathermap_api_key", sa.String(512), nullable=True),
        sa.Column(
            "genai_chat_enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "weather_enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "sso_enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("updated_by", sa.String(320), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("instance_settings")
