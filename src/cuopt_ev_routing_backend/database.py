# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Async SQLAlchemy engine + session factory.

Mirrors :mod:`accelerator_pack_auth_service.database`'s engine factory so the
two services pick the same backend (sqlite / postgres / oracle) from analogous
``CUOPT_*`` envs. Schema is bootstrapped via ``alembic upgrade head`` in
:func:`init_db` — never ``Base.metadata.create_all`` (avoids the schema-drift
class of bug that previously bit auth-service on Oracle).
"""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cuopt_ev_routing_backend.config import settings


def _build_engine():
    """Build the async engine based on config."""
    db_type = settings.database_type

    if db_type == "auto":
        if settings.oracle_connection_string:
            db_type = "oracle"
        elif "postgresql" in settings.database_url:
            db_type = "postgres"
        else:
            db_type = "sqlite"

    if db_type == "oracle":
        return create_async_engine(
            "oracle+oracledb://",
            thick_mode=False,
            connect_args={
                "user": settings.oracle_user,
                "password": settings.oracle_password,
                "dsn": settings.oracle_connection_string,
            },
            pool_size=5,
            max_overflow=10,
            echo=False,
        )
    if db_type == "postgres":
        return create_async_engine(
            settings.database_url,
            pool_size=5,
            max_overflow=10,
            echo=False,
        )
    # sqlite (default for dev + tests)
    return create_async_engine(settings.database_url, echo=False)


engine = _build_engine()
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _run_alembic_upgrade() -> None:
    """Synchronous: run ``alembic upgrade head`` against the runtime DB.

    ``alembic/env.py`` reads :mod:`config.settings` directly, so the upgrade
    targets whatever database the app is configured for.
    """
    from alembic import command
    from alembic.config import Config

    # Resolve alembic.ini + alembic/ via two candidate roots:
    #   - Path.cwd(): correct in the container (Dockerfile sets WORKDIR=/app
    #     and ships alembic.ini + alembic/ there).
    #   - parents[2] of this module: correct in dev/test source layout
    #     (src/cuopt_ev_routing_backend/ → repo root).
    # When the package is pip-installed (site-packages), parents[2] resolves
    # to <python-prefix>/, which lacks alembic/. cwd is the reliable handle.
    candidates = [Path.cwd(), Path(__file__).resolve().parents[2]]
    repo_root = next((p for p in candidates if (p / "alembic.ini").exists()), candidates[0])
    ini_path = repo_root / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(repo_root / "alembic"))
    command.upgrade(cfg, "head")


async def init_db() -> None:
    """Run database migrations to ensure schema is current.

    ``alembic env.py`` uses ``asyncio.run()`` internally, which can't be
    invoked from inside an active event loop. Dispatch the synchronous
    alembic call to a worker thread.
    """
    await asyncio.to_thread(_run_alembic_upgrade)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yield an async session bound to a request."""
    async with async_session() as session:
        yield session
