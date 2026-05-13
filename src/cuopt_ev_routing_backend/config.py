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

    # Auth-service JWT validation (RS256 via JWKS). Tokens are verified locally
    # by fetching each trusted issuer's JWKS and looking the token's `kid` up
    # against the cache. Fail-closed defaults: main._validate_safety() rejects
    # auth_require_auth=False unless debug=True, and rejects auth_require_auth=True
    # with an empty trusted-issuers list.
    auth_trusted_issuers: str = ""
    auth_jwks_cache_ttl: int = 3600
    auth_require_auth: bool = True
    auth_token_audience: str | None = None

    # CORS. Empty default forces operators to set CUOPT_ALLOWED_ORIGINS explicitly.
    # main.py disables allow_credentials when any wildcard ("*") is in the list —
    # the combination is rejected by the CORS spec and silently broken in browsers.
    allowed_origins: str = ""
    rate_limit: str = "60/minute"

    # Database (instance_settings table for admin-managed runtime config).
    # ``auto`` selects oracle when oracle_connection_string is set, otherwise
    # falls back to ``database_url`` (sqlite by default — fine for dev/tests).
    database_type: str = "auto"
    database_url: str = "sqlite+aiosqlite:///./cuopt.db"
    oracle_connection_string: str = Field("", json_schema_extra={"sensitive": True})
    oracle_user: str = ""
    oracle_password: str = Field("", json_schema_extra={"sensitive": True})  # noqa: S105


settings = Settings()
