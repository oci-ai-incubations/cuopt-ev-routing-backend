---
name: build-containers
description: Build and push the backend Docker container.
user-invocable: true
allowed-tools: Bash, Read
---

# Build Container

Build the Docker image for the cuOpt EV routing backend.

## Commands

From the repo root:

```bash
cd "$(git rev-parse --show-toplevel)"
docker build --network=host --platform linux/amd64 \
  -t iad.ocir.io/iduyx1qnmway/corrino-devops-repository/cuopt-ev-routing-backend:test \
  --push \
  -f Dockerfile .
```

## Notes

- The `--push` flag pushes to OCIR immediately. Drop it for a local-only build.
- The tag `:test` is the default. Use a semver tag (read from `VERSION`) for
  release builds.
- Container registry: `iad.ocir.io/iduyx1qnmway/corrino-devops-repository/`
