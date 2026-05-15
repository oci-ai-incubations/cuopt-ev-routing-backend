# CLAUDE.md — cuOpt EV Routing Backend

This file provides guidance to Claude Code when working in this repository.

See `.claude/rules/backend.md` for coding conventions and `.claude/rules/testing.md`
for test guidelines.

## Overview

FastAPI backend for the cuOpt EV routing application. This service was split
out from the Express.js server previously in `cuopt-ev-routing-frontend/server/`
and is the canonical home for the application's API surface.

The service is a thin proxy/BFF in front of three upstream services:

- **NVIDIA cuopt** — the GPU-accelerated VRP solver. Accessed via `CUOPT_CUOPT_ENDPOINT`.
- **LlamaStack** — LLM gateway used for chat / route explanations. Accessed via `CUOPT_LLAMASTACK_ENDPOINT`.
- **OpenWeatherMap** — weather data for weather-aware routing. Falls back to
  generated mock weather when no key is configured.

No database is used — add one only when persistence is required.

## Authentication

All `/api/*` routes are protected by an RS256 JWT dependency
(`cuopt_ev_routing_backend.auth.get_current_user`) that validates tokens
issued by the shared `accelerator-pack-auth-service` or federated IdPs
(Oracle IDCS, Microsoft Entra). Verification is local — for each trusted
issuer the BE fetches the OIDC discovery doc at
`{issuer}/.well-known/openid-configuration`, reads the `jwks_uri` field,
fetches the JWKS at that URL, caches it for `CUOPT_AUTH_JWKS_CACHE_TTL`
seconds, and looks the token's `kid` header up against the cache.
Discovery-based resolution lets IDCS publish JWKS at
`/admin/v1/SigningCert/jwk` and Entra at `/{tenant}/discovery/v2.0/keys`
— hardcoding `/.well-known/jwks.json` only works for auth-service. Tokens
must carry an `aud` claim matching one of the values in
`CUOPT_AUTH_TOKEN_AUDIENCE` (RFC 9068 §4). Scope authorization reads the
`scope` claim first (RFC 6749), falling back to `scp` (Entra delegated) or
`roles` (Entra app-roles) for federated tokens. Set
`CUOPT_AUTH_REQUIRE_AUTH=true` in deployed environments. The default
(`true` in production; `false` only when `CUOPT_DEBUG=true`) returns a
synthetic admin user without checking the token — local-dev convenience.

`/healthz` and `/readyz` are public and not gated by auth.

## Architecture

```
src/cuopt_ev_routing_backend/
├── main.py                 # FastAPI app + CORS + router registration + health probes
├── config.py               # Pydantic Settings (CUOPT_ env prefix)
├── auth.py                 # RS256 JWT dependency (get_current_user, require_role)
├── jwks.py                 # Per-issuer JWKS fetch + cache (hardened https-only opener)
├── api/
│   └── routes/
│       ├── config.py       # GET  /api/config (googleMapsApiKey)
│       ├── cuopt.py        # /api/cuopt/{health,request,solution/{id}}, /api/cuopt-health
│       ├── genai.py        # /api/models, /api/genai/{chat,health}
│       └── weather.py      # /api/weather/{current,forecast,alerts,health}
├── services/               # httpx async clients for upstream services
│   ├── cuopt.py
│   ├── genai.py            # + transform_to_llamastack_format / extract_response_text
│   └── weather.py          # + generate_mock_weather
└── schemas/
    └── genai.py            # ChatRequestEnvelope
```

## Quick Reference

```bash
pip install -r requirements-dev.txt
pip install -e .
uvicorn cuopt_ev_routing_backend.main:app --reload   # dev server on :8080
ruff check src/ tests/                               # lint
ruff format src/ tests/                              # format
pytest tests/ -v --cov-fail-under=80                 # unit tests
RUN_INTEGRATION_TESTS=1 pytest tests/integration/ -v # integration tests
```

## Environment Variables

All prefixed with `CUOPT_`. Defaults are in `src/cuopt_ev_routing_backend/config.py`.

| Var | Purpose |
|---|---|
| `CUOPT_DEBUG` | When true, exposes `/api/docs` etc. |
| `CUOPT_CUOPT_ENDPOINT` | Upstream NVIDIA cuopt service URL |
| `CUOPT_LLAMASTACK_ENDPOINT` | Upstream LlamaStack URL |
| `CUOPT_LLAMASTACK_MODEL` | Default model id (FE can override per-request) |
| `CUOPT_GOOGLE_MAPS_API_KEY` | Returned via `/api/config` to the SPA |
| `CUOPT_OPENWEATHERMAP_API_KEY` | Real weather provider key; empty = mock mode |
| `CUOPT_AUTH_TRUSTED_ISSUERS` | Comma-separated allowlist of trusted issuer URLs (each must be `https://`). Tokens carrying an `iss` claim outside this list are rejected before any network IO. Each issuer's JWKS URL is resolved via its OIDC discovery doc at `{iss}/.well-known/openid-configuration` (`jwks_uri` field). |
| `CUOPT_AUTH_JWKS_CACHE_TTL` | JWKS cache TTL in seconds (default `3600`). Applies to both the OIDC discovery doc and the JWKS itself. A kid-miss within the TTL triggers exactly one JWKS refresh (discovery stays cached). |
| `CUOPT_AUTH_REQUIRE_AUTH` | Default `true` in production; allowed `false` only when `CUOPT_DEBUG=true` |
| `CUOPT_AUTH_TOKEN_AUDIENCE` | Comma-separated list of allowed `aud` claim values (default `cuopt`). Audience verification is always on (RFC 9068 §4). Tokens whose `aud` matches any element validate; tokens missing `aud` or matching none are rejected. Use multiple values to trust tokens from multiple IdPs (e.g. `cuopt,https://cuopt.example.com/api/`). |
| `CUOPT_ALLOWED_ORIGINS` | Comma-separated; `*` only safe for dev |
| `CUOPT_RATE_LIMIT` | slowapi default rate limit |

The double-`CUOPT_CUOPT_*` envs come from `pydantic-settings`'s `env_prefix="CUOPT_"`
combined with field names that already begin with `cuopt_`. The Terraform
blueprint sets these env vars on the deployed pod.
