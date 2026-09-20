#!/usr/bin/env bash
set -euo pipefail

# The image runs as uid 1000, not root (ADR 0011 item 5), and a bind mount
# keeps the host directory's ownership rather than the image's -- so the host
# side has to be writable by that uid before the container can create app.db.
mkdir -p data
chmod 0777 data

docker build -t opptrail .
docker rm -f opptrail >/dev/null 2>&1 || true
docker run \
  --name opptrail \
  --env-file .env \
  -p "${PORT:-8000}:8000" \
  -v "$(pwd)/data:/data" \
  opptrail
