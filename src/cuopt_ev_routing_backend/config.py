# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""Application configuration.

All settings use the ``CUOPT_`` environment variable prefix.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CUOPT_", env_file=".env", extra="ignore")

    app_name: str = "cuOpt EV Routing Backend"
    debug: bool = False

    cuopt_endpoint: str = "https://cuopt-2-cuopt.137-131-27-21.nip.io"
    google_maps_api_key: str = ""

    admin_username: str = "admin"
    admin_password: str = "admin"  # noqa: S105 — placeholder default; override with CUOPT_ADMIN_PASSWORD

    allowed_origins: str = "*"
    rate_limit: str = "60/minute"


settings = Settings()
