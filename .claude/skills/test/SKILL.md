---
name: test
description: Run pytest for the backend.
user-invocable: true
allowed-tools: Bash, Read, Grep
argument-hint: [test-filter]
---

# Test

Run the pytest suite. Integration tests are excluded unless invoked via the
`/integration-test` skill.

## Arguments

- `$0` (optional) — pytest `-k` filter, e.g. `test_healthz`.

## Commands

With a filter:

```bash
cd "$(git rev-parse --show-toplevel)"
pytest tests/ -v --ignore=tests/integration -k "$0"
```

Without a filter (run everything):

```bash
cd "$(git rev-parse --show-toplevel)"
pytest tests/ -v --ignore=tests/integration
```

If running from a venv, prefix with `.venv/bin/`.

## On Failure

- Show the failing test name and error output.
- Investigate the test file and the source code it covers.
- Suggest a fix.
