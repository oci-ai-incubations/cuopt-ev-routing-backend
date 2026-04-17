# Backend Rules

## Code Style
- Python 3.12+. Ruff lint + format with line-length=100.
- Type hints required on all function signatures.
- Docstrings required on all public functions.
- Use `StrEnum` (not `str, Enum`) for string enumerations.
- Use `datetime.now(UTC)` (not `timezone.utc`).
- Run `ruff check --fix src/ tests/` before committing.

## FastAPI Conventions
- Application code lives in `src/cuopt_ev_routing_backend/`.
- Route modules go in `src/cuopt_ev_routing_backend/api/routes/` (create as needed). Register them in `main.py`.
- Use Pydantic v2 models for all request/response schemas. Schemas go in `src/cuopt_ev_routing_backend/schemas/`.
- Business logic goes in `src/cuopt_ev_routing_backend/services/`, not in route handlers.
- Prefix all API routes with `/api` (via the router prefix in `main.py`).
- Health probes (`/healthz`, `/readyz`) are at the root level, not under `/api`.

## Environment Variables
- All env vars are prefixed with `CUOPT_` and loaded via Pydantic Settings in `src/cuopt_ev_routing_backend/config.py`.

## Optimization
- The only optimizer allowed is [NVIDIA cuOpt](https://github.com/NVIDIA/cuopt). Do not introduce alternative solvers.
- Downstream cuOpt calls go through a dedicated service module and are configured via `CUOPT_ENDPOINT`.

## Testing
- Use pytest with the FastAPI `TestClient` fixture from `tests/conftest.py`.
- Test files go in `tests/` with the `test_` prefix.
- Integration tests go in `tests/integration/` and are gated by `RUN_INTEGRATION_TESTS=1`.
- Run: `pytest tests/ -v --ignore=tests/integration`
