# Security Rules

These rules apply to all code changes in this repo.

## Secrets & Configuration

- Never hardcode secrets, passwords, API keys, or connection strings in source code. All sensitive values must come from environment variables via `src/cuopt_ev_routing_backend/config.py`.
- Never commit `.env` files, credentials, private keys, or wallets. The `.gitignore` blocks `.env`, `.env.*`, `*.pem`, `*.key`.
- Mark sensitive settings with `json_schema_extra={"sensitive": True}` in Pydantic Settings so they are redacted in logs and debug output.

## Input Validation

- Validate all user input at the API boundary using Pydantic models. Never trust raw request data.
- Use Pydantic `Field` constraints (`ge`, `le`, `gt`, `min_length`, `max_length`) to enforce value bounds on numeric and string inputs.
- Never pass user-supplied strings into `eval()`, `exec()`, or shell commands.

## CORS

- CORS origins are configured via `CUOPT_ALLOWED_ORIGINS` (comma-separated). Never use `allow_origins=["*"]` in production.
- Only `GET` and `POST` methods are allowed. Only `Content-Type` and `Authorization` headers are allowed.

## Rate Limiting

- All routes are rate-limited via slowapi (default: `CUOPT_RATE_LIMIT`, currently `60/minute`).
- Upload or other expensive routes should have stricter per-route limits.

## Security Headers

- Add a `SecurityHeadersMiddleware` in `main.py` that attaches the following headers to all responses when introducing public-facing endpoints:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `X-XSS-Protection: 1; mode=block`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Permissions-Policy: camera=(), microphone=(), geolocation=()`
  - `Strict-Transport-Security` (production only, when `CUOPT_DEBUG=false`)

## API Surface

- OpenAPI docs (`/api/docs`, `/api/redoc`, `/api/openapi.json`) are disabled when `CUOPT_DEBUG=false`. Must not be exposed in production.
- Health probes (`/healthz`, `/readyz`) do not require authentication and must not expose internal details.

## Dependencies

- Run `pip-audit` to scan Python dependencies for known vulnerabilities before releases.
- Ruff is configured with the `S` (bandit) rule set for static security analysis. Do not suppress `S` rules without a comment explaining why.

## Containers

- The Dockerfile runs as a non-root user (`appuser`, UID 1001).
- Base images use `-slim` variants to minimize attack surface.

## Security Scanning Checklist

Before any release, run `/security-scan` which covers:
1. `ruff check --select S` — bandit static analysis for Python security issues.
2. `pip-audit` — known vulnerability scan on Python dependencies.
3. Verify `.env` and other secret files are not committed (`git status` check).
