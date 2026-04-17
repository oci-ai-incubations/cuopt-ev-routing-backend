---
name: lint
description: Run ruff lint and format checks (includes bandit security rules).
user-invocable: true
allowed-tools: Bash, Read
---

# Lint

Run the full ruff lint + format check suite. Ruff's `S` rules provide bandit
security static analysis.

## Commands

```bash
cd "$(git rev-parse --show-toplevel)"
ruff check src/ tests/
ruff format --check src/ tests/
```

If running from a venv, prefix with `.venv/bin/`.

## On Failure

- **ruff check**: Run `ruff check --fix src/ tests/` to auto-fix, then show
  remaining issues. Do not suppress `S` (bandit) rules without a comment
  explaining why.
- **ruff format**: Run `ruff format src/ tests/` to auto-fix.
