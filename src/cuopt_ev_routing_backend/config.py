# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Application configuration.

All settings use the ``CUOPT_`` environment variable prefix. So a field named
``llamastack_endpoint`` is loaded from ``CUOPT_LLAMASTACK_ENDPOINT``.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CUOPT_", env_file=".env", extra="ignore")

    app_name: str = "cuOpt EV Routing Backend"
    debug: bool = False

    # Upstream services
    cuopt_endpoint: str = "https://cuopt-2-cuopt.137-131-27-21.nip.io"
    llamastack_endpoint: str = "http://localhost:8321"
    llamastack_model: str = ""

    # TLS verification for outbound httpx calls to in-cluster services.
    # Default True for prod safety. Set CUOPT_TLS_VERIFY=false when the
    # in-cluster cuopt / llamastack services present self-signed certs.
    tls_verify: bool = True

    # Runtime config exposed to the frontend
    google_maps_api_key: str = Field("", json_schema_extra={"sensitive": True})

    # Weather provider
    openweathermap_api_key: str = Field("", json_schema_extra={"sensitive": True})

    # Legacy admin credentials (Express had a /api/auth/login endpoint that used
    # these — we no longer expose login here; auth-service handles it. Kept so
    # operators who still set these envs do not get errors).
    admin_username: str = ""
    admin_password: str = Field("", json_schema_extra={"sensitive": True})  # noqa: S105 — empty default

    # Auth-service JWT validation (HS256)
    auth_jwt_secret: str = Field("", json_schema_extra={"sensitive": True})  # noqa: S105 — empty default
    auth_jwt_algorithm: str = "HS256"
    auth_require_auth: bool = False
    auth_token_audience: str | None = None

    allowed_origins: str = "*"
    rate_limit: str = "60/minute"


settings = Settings()
