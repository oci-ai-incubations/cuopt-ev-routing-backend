# Testing Rules

## Unit tests (pytest)
- Test files go in `tests/` with the `test_` prefix.
- Use the `client` fixture from `tests/conftest.py` for endpoint tests.
- Run all: `pytest tests/ -v --ignore=tests/integration`
- Run single: `pytest tests/ -v -k "test_name"`
- Always run `ruff check` before running tests — lint errors often cause import-time test failures.

## Integration tests (pytest + httpx.AsyncClient)
- Test files go in `tests/integration/` with the `test_int_` prefix.
- Use the async `integration_client` fixture from `tests/integration/conftest.py`.
- Gated by `RUN_INTEGRATION_TESTS=1` — will skip otherwise.
- Decorate individual tests with `@pytest.mark.integration`.
- Module-level `pytestmark = pytest.mark.asyncio(loop_scope="session")` so tests share the session event loop.
- Run all: `RUN_INTEGRATION_TESTS=1 pytest tests/integration/ -v --tb=short`

## Coverage
- Target ≥80% line coverage on `cuopt_ev_routing_backend` (enforced by CI via `--cov-fail-under=80`).
- Integration tests are excluded from the coverage run — coverage is measured against unit tests only.

## General
- Write tests for all new endpoints, services, and non-trivial logic.
- Tests must be fast and must not depend on unmocked external services — mock at the service boundary (`httpx`, etc.) for unit tests; use `integration_client` for full-stack tests.
