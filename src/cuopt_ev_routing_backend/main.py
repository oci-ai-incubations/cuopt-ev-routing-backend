# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cuopt_ev_routing_backend import __version__
from cuopt_ev_routing_backend.api.routes import admin as admin_routes
from cuopt_ev_routing_backend.api.routes import config as config_routes
from cuopt_ev_routing_backend.api.routes import cuopt as cuopt_routes
from cuopt_ev_routing_backend.api.routes import genai as genai_routes
from cuopt_ev_routing_backend.api.routes import weather as weather_routes
from cuopt_ev_routing_backend.config import settings
from cuopt_ev_routing_backend.database import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Run ``alembic upgrade head`` so ``instance_settings`` exists before traffic."""
    await init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    docs_url="/api/docs" if settings.debug else None,
    redoc_url="/api/redoc" if settings.debug else None,
    openapi_url="/api/openapi.json" if settings.debug else None,
    lifespan=lifespan,
)

origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(config_routes.router)
app.include_router(cuopt_routes.router)
app.include_router(genai_routes.router)
app.include_router(weather_routes.router)
app.include_router(admin_routes.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness probe — public, no auth required."""
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> dict[str, str]:
    """Readiness probe — public, no auth required."""
    return {"status": "ok"}
