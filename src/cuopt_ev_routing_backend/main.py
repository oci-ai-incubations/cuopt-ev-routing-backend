# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from cuopt_ev_routing_backend import __version__
from cuopt_ev_routing_backend.api.routes import admin as admin_routes
from cuopt_ev_routing_backend.api.routes import config as config_routes
from cuopt_ev_routing_backend.api.routes import cuopt as cuopt_routes
from cuopt_ev_routing_backend.api.routes import genai as genai_routes
from cuopt_ev_routing_backend.api.routes import weather as weather_routes
from cuopt_ev_routing_backend.config import settings
from cuopt_ev_routing_backend.database import init_db


def _validate_safety() -> None:
    """Refuse to start with unsafe configuration.

    Two failure modes this guards against:
    - Auth disabled outside dev: a missing CUOPT_AUTH_REQUIRE_AUTH env in
      production would silently fall back to the synthetic-admin path and
      serve /api/* unauthenticated.
    - Auth enabled with no secret: legible 401-and-misconfigured errors
      mid-request are worse than refusing to start.
    """
    if not settings.auth_require_auth and not settings.debug:
        raise RuntimeError(
            "CUOPT_AUTH_REQUIRE_AUTH=false is only permitted when CUOPT_DEBUG=true. "
            "Refusing to start (would serve /api/* unauthenticated in production)."
        )
    if settings.auth_require_auth and not settings.auth_jwt_secret:
        raise RuntimeError("CUOPT_AUTH_REQUIRE_AUTH=true requires CUOPT_AUTH_JWT_SECRET to be set.")


_validate_safety()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Run ``alembic upgrade head`` so ``instance_settings`` exists before traffic."""
    await init_db()
    yield


OPENAPI_TAGS = [
    {"name": "Health", "description": "Liveness and readiness probes — public."},
    {
        "name": "Configuration",
        "description": "Runtime configuration values consumed by the SPA on boot.",
    },
    {
        "name": "cuOpt",
        "description": "Proxy routes for the upstream NVIDIA cuOpt VRP solver.",
    },
    {
        "name": "GenAI",
        "description": "LlamaStack-backed model discovery and chat used for route explanations.",
    },
    {
        "name": "Weather",
        "description": "OpenWeatherMap proxy with mock fallback for weather-aware routing.",
    },
    {
        "name": "Admin",
        "description": "Admin-only runtime configuration of API keys and feature flags.",
    },
]


_OPENAPI_DESCRIPTION = (
    "FastAPI backend for the cuOpt EV routing accelerator pack. Proxies the "
    "upstream NVIDIA cuOpt VRP solver, LlamaStack chat, and OpenWeatherMap, and "
    "owns the admin-managed `instance_settings` runtime configuration. All "
    "`/api/*` routes require an HS256 JWT issued by `accelerator-pack-auth-service`."
)


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=_OPENAPI_DESCRIPTION,
    docs_url="/api/docs" if settings.debug else None,
    redoc_url="/api/redoc" if settings.debug else None,
    openapi_url="/api/openapi.json" if settings.debug else None,
    contact={
        "name": "OCI AI Accelerator Team",
        "url": "https://github.com/oci-ai-incubations/cuopt-ev-routing-backend",
    },
    license_info={
        "name": "Universal Permissive License v1.0",
        "url": "https://oss.oracle.com/licenses/upl",
    },
    servers=[
        {"url": "http://localhost:8080", "description": "Local development"},
    ],
    openapi_tags=OPENAPI_TAGS,
    lifespan=lifespan,
)


def custom_openapi() -> dict:
    """Return the OpenAPI schema with a bearerAuth security scheme applied globally.

    Public endpoints opt out per-route by passing
    ``openapi_extra={"security": []}`` in their decorator; everything else
    inherits the default Bearer requirement so the Swagger UI lock icon
    reflects reality.
    """
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=OPENAPI_TAGS,
        servers=app.servers,
        contact=app.contact,
        license_info=app.license_info,
    )
    schema.setdefault("components", {})["securitySchemes"] = {
        "bearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "JWT access token issued by `accelerator-pack-auth-service` (`POST /auth/login`)."
            ),
        }
    }
    schema["security"] = [{"bearerAuth": []}]
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi

origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
# CORS spec forbids allow_credentials=true with wildcard origins; browsers
# reject the preflight. Force credentials off if any wildcard slipped in.
allow_credentials = not any(o == "*" for o in origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=allow_credentials,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type", "Authorization"],
)

# Rate limiting. Default is settings.rate_limit (e.g. "60/minute") per-IP.
# Per-route stricter limits can decorate routes with @limiter.limit(...).
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.rate_limit])
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(_request: Request, _exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)


# Security headers — applied to every response. HSTS is conditional on a
# non-debug runtime (HTTP is fine in local dev; production runs behind the
# OKE ingress with TLS terminated upstream).
@app.middleware("http")
async def _security_headers(request: Request, call_next) -> Response:
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    )
    if not settings.debug:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


app.include_router(config_routes.router)
app.include_router(cuopt_routes.router)
app.include_router(genai_routes.router)
app.include_router(weather_routes.router)
app.include_router(admin_routes.router)


@app.get(
    "/healthz",
    summary="Liveness probe",
    description=(
        "Kubernetes liveness probe. Returns `{status: ok}` whenever the process "
        "is running. Public — no authentication required."
    ),
    tags=["Health"],
    responses={200: {"description": "Process is alive"}},
    openapi_extra={"security": []},
)
def healthz() -> dict[str, str]:
    """Liveness probe — public, no auth required."""
    return {"status": "ok"}


@app.get(
    "/readyz",
    summary="Readiness probe",
    description=(
        "Kubernetes readiness probe. Returns `{status: ok}` once the lifespan "
        "has completed `alembic upgrade head` and the app is ready to serve "
        "traffic. Public — no authentication required."
    ),
    tags=["Health"],
    responses={200: {"description": "Service is ready"}},
    openapi_extra={"security": []},
)
def readyz() -> dict[str, str]:
    """Readiness probe — public, no auth required."""
    return {"status": "ok"}
