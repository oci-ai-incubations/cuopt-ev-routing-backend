# CLAUDE.md — cuOpt EV Routing Backend

This file provides guidance to Claude Code when working in this repository.

See `.claude/rules/backend.md` for coding conventions and `.claude/rules/testing.md`
for test guidelines.

## Overview

FastAPI backend for the cuOpt EV routing application. This service was split
out from the Express.js server previously in `cuopt-ev-routing-frontend/server`.

No database is used yet — add one only when persistence is required.

## Quick Reference

```bash
pip install -r requirements-dev.txt
pip install -e .
uvicorn cuopt_ev_routing_backend.main:app --reload   # dev server on :8080
ruff check src/ tests/                               # lint
ruff format src/ tests/                              # format
pytest tests/ -v --cov-fail-under=80                 # unit tests
RUN_INTEGRATION_TESTS=1 pytest tests/integration/ -v # integration tests
```

## Environment Variables

Prefixed with `CUOPT_`. See `src/cuopt_ev_routing_backend/config.py` for the
full list and defaults.
