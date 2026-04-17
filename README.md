# cuOpt EV Routing Backend

FastAPI backend for the cuOpt EV routing application. Split from the Express.js
server that previously lived in `cuopt-ev-routing-frontend`.

## Quick Start

```bash
pip install -r requirements-dev.txt
pip install -e .
uvicorn cuopt_ev_routing_backend.main:app --host 0.0.0.0 --port 8080 --reload
```

## Development

```bash
ruff check src/ tests/                   # lint
ruff format --check src/ tests/          # format check
pytest tests/ -v --cov-fail-under=80     # unit tests with coverage
pip-audit -r requirements.txt            # dependency vulnerability scan
python scripts/check_license_headers.py  # verify license headers
```

### Pre-commit Hooks

This repo uses [pre-commit](https://pre-commit.com/) to run ruff and the
license-header check before every commit. Install once after cloning:

```bash
pip install pre-commit
pre-commit install
```

To run all hooks manually against the full tree:

```bash
pre-commit run --all-files
```

## Integration Tests

```bash
RUN_INTEGRATION_TESTS=1 pytest tests/integration/ -v
```

## Docker

```bash
docker build -t cuopt-ev-routing-backend:local .
docker run --rm -p 8080:8080 cuopt-ev-routing-backend:local
```

## Project Layout

```
src/cuopt_ev_routing_backend/  # application code
tests/                         # unit tests
tests/integration/             # integration tests (RUN_INTEGRATION_TESTS=1)
docs/                          # documentation
scripts/                       # repo-local tooling (license-header check, etc.)
.github/workflows/             # CI pipelines
```

## Contributing

Contributions are welcome. Before opening a pull request, please read
[CONTRIBUTING.md](./CONTRIBUTING.md) for the Oracle Contributor Agreement (OCA)
workflow and the `Signed-off-by` commit-message requirement.

## Security

Do **not** open GitHub Issues for security vulnerabilities. See
[SECURITY.md](./SECURITY.md) for the Oracle responsible-disclosure process.

## License

Copyright © 2026, Oracle and/or its affiliates.

Released under the Universal Permissive License v 1.0 (UPL). See
[LICENSE.md](./LICENSE.md) for the full text, or the short reference at
<https://oss.oracle.com/licenses/upl>.
