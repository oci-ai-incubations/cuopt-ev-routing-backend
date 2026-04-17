---
name: integration-test
description: Run integration tests (gated by RUN_INTEGRATION_TESTS=1) and guide adding new integration tests.
user-invocable: true
allowed-tools: Bash, Read, Grep, Edit, Write
argument-hint: [test-filter]
---

# Integration Test

Runs the backend integration test suite. Integration tests are gated behind
`RUN_INTEGRATION_TESTS=1` and exercise the FastAPI app end-to-end via
`httpx.ASGITransport` (and any downstream services like cuOpt).

## Arguments

- `$0` (optional) — pytest `-k` filter, e.g. `test_int_health`.

## Run all integration tests

```bash
cd "$(git rev-parse --show-toplevel)"
RUN_INTEGRATION_TESTS=1 pytest tests/integration/ -v --tb=short
```

## Run with filter

```bash
cd "$(git rev-parse --show-toplevel)"
RUN_INTEGRATION_TESTS=1 pytest tests/integration/ -v --tb=short -k "$0"
```

## On Failure

1. Read the full error output — it names the failing test and assertion.
2. Decide whether the failure is a real app bug or a test-assumption mismatch.
3. Re-run the failing test with `--tb=long` for a full traceback:
   ```bash
   RUN_INTEGRATION_TESTS=1 pytest tests/integration/ -v --tb=long \
     -k "failing_test_name"
   ```

---

## Adding Integration Tests for New Features

When implementing a feature that changes the API surface or crosses process
boundaries, add a corresponding integration test.

### Decision: does this feature need an integration test?

Add an integration test when the feature:
- Adds a new API endpoint or changes an existing endpoint's response shape.
- Calls a downstream service (cuOpt, Google Maps, etc.).
- Changes middleware, CORS, auth, or rate-limiting behavior.

Skip the integration test (a unit test is sufficient) when the feature:
- Is pure business logic with no external I/O.
- Is already fully covered by a unit test with the same assertions.

### Where to add the test

| Feature type | File |
|---|---|
| New health/readiness signal | `tests/integration/test_int_health.py` |
| New standalone endpoint / route module | `tests/integration/test_int_<feature>.py` |

### Test structure

```python
import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.mark.integration
async def test_<feature>_<scenario>(integration_client):
    """One-line description of what this verifies."""
    resp = await integration_client.post("/api/<endpoint>", json={...})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["<key>"] == <expected>
```

### Checklist before committing

- [ ] Decorated with `@pytest.mark.integration`.
- [ ] Uses the `integration_client` fixture (async httpx), not the unit-test
      `client` fixture.
- [ ] Module-level `pytestmark = pytest.mark.asyncio(loop_scope="session")` so
      tests share the session event loop.
- [ ] Runs cleanly:
      `RUN_INTEGRATION_TESTS=1 pytest tests/integration/ -v -k "test_name"`.
