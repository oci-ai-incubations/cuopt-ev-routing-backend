---
name: coverage
description: Run pytest with coverage. Fails if coverage drops below 80%.
user-invocable: true
allowed-tools: Bash, Read, Grep
---

# Code Coverage

Run the test suite with coverage and fail if coverage drops below 80%.

## Commands

```bash
cd "$(git rev-parse --show-toplevel)"
pytest tests/ -v \
  --ignore=tests/integration \
  --cov=cuopt_ev_routing_backend \
  --cov-report=term-missing \
  --cov-fail-under=80
```

If running from a venv, prefix with `.venv/bin/` (or activate the venv first).

## On Failure

- Identify the files with lowest coverage in the `term-missing` output.
- Show which uncovered lines/functions need tests.
- Suggest specific unit tests to add to reach the 80% threshold.
