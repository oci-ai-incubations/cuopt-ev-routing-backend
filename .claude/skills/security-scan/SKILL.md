---
name: security-scan
description: Run security scans — ruff bandit rules, pip-audit, and secrets check.
user-invocable: true
allowed-tools: Bash, Read, Grep
---

# Security Scan

Run all security checks for this repo. Report all findings together.

## Steps

### 1. Python static analysis (bandit via ruff)

```bash
cd "$(git rev-parse --show-toplevel)"
ruff check --select S src/
```

### 2. Python dependency audit

```bash
cd "$(git rev-parse --show-toplevel)"
pip-audit -r requirements.txt
```

Install `pip-audit` if missing: `pip install pip-audit`.

### 3. Secrets check

Verify no secret files are staged:

```bash
cd "$(git rev-parse --show-toplevel)"
git diff --cached --name-only | grep -iE '\.(env|pem|key|p12|jks|keystore)$' \
  || echo "No secret files staged"
```

Use the `Grep` tool to search for hardcoded credentials in `src/`. Pattern:
`(password|secret|api_key|token)\s*=\s*["'][^"']+["']`. Exclude
`src/cuopt_ev_routing_backend/config.py` (which only contains empty defaults).

## Reporting

Summarize findings as:
- **PASS** — no issues.
- **WARN** — advisory findings, review recommended.
- **FAIL** — vulnerabilities or hardcoded secrets found. Must fix before deploy.

For any FAIL, suggest specific remediations.
