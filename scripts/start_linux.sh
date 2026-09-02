#!/usr/bin/env bash
set -euo pipefail

docker build -t opptrail .
docker rm -f opptrail >/dev/null 2>&1 || true
docker run \
  --name opptrail \
  --env-file .env \
  -p "${PORT:-8000}:8000" \
  -v "$(pwd)/data:/data" \
  opptrail
