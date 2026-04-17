---
name: dev
description: Start the FastAPI backend dev server.
user-invocable: true
allowed-tools: Bash, Read
---

# Dev Server

Start the FastAPI dev server for local development. Hot-reload is enabled.

## Commands

```bash
cd "$(git rev-parse --show-toplevel)"
uvicorn cuopt_ev_routing_backend.main:app --reload --host 0.0.0.0 --port 8080
```

If running from a venv, activate it first (`source .venv/bin/activate`) or
invoke `.venv/bin/uvicorn` directly.

Use `run_in_background=true` so the server stays up while you work on other
things.

## Notes

- Requires a Python venv with dependencies installed:
  `pip install -r requirements-dev.txt && pip install -e .`
- Set `CUOPT_DEBUG=true` to expose `/api/docs`, `/api/redoc`, and
  `/api/openapi.json`.
- All settings use the `CUOPT_` env var prefix — see
  `src/cuopt_ev_routing_backend/config.py`.
