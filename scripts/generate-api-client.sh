#!/usr/bin/env bash
# Regenerates frontend/lib/api-types.ts from the FastAPI OpenAPI schema.
#
# Usage:
#   scripts/generate-api-client.sh          # write frontend/lib/api-types.ts
#   scripts/generate-api-client.sh --check  # fail if the committed file is stale
set -euo pipefail

cd "$(dirname "$0")/.."

SCHEMA="$(mktemp)"
trap 'rm -f "$SCHEMA"' EXIT
(cd backend && uv run python -m app.export_openapi) > "$SCHEMA"

if [ "${1:-}" = "--check" ]; then
  OUT="$(mktemp)"
  trap 'rm -f "$SCHEMA" "$OUT"' EXIT
  (cd frontend && npx --no-install openapi-typescript "$SCHEMA" -o "$OUT")
  if ! diff -u frontend/lib/api-types.ts "$OUT"; then
    echo "frontend/lib/api-types.ts is stale — run scripts/generate-api-client.sh" >&2
    exit 1
  fi
  echo "frontend/lib/api-types.ts is up to date."
else
  (cd frontend && npx --no-install openapi-typescript "$SCHEMA" -o lib/api-types.ts)
  echo "Regenerated frontend/lib/api-types.ts"
fi
