# CI Checks — Pre-push Workflow

Before every `git push`, run all CI checks locally. Each check is a separate Bash call — never chain commands with `&&`.

## Directory setup

Always `cd` to the repo root as its own Bash call. The working directory persists between calls.

```bash
cd "$(git rev-parse --show-toplevel)"
```

## Checks (from repo root)

Use `.venv/bin/<tool>` to invoke venv tools — no `source .venv/bin/activate` needed. If your venv lives elsewhere, adjust accordingly.

1. `ruff check --fix src/ tests/`
2. `ruff format src/ tests/`
3. `ruff check src/ tests/` (verify no remaining issues)
4. `ruff format --check src/ tests/` (verify formatting)
5. `pytest tests/ -v --ignore=tests/integration --cov=cuopt_ev_routing_backend --cov-report=term-missing --cov-fail-under=80`
6. `pip-audit -r requirements.txt`

## Integration tests (optional, before opening a PR)

```bash
RUN_INTEGRATION_TESTS=1 pytest tests/integration/ -v --tb=short
```

## Order

Run all checks above before pushing. Fix any failures before pushing rather than relying on CI to surface them.
