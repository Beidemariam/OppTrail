#!/usr/bin/env bash
# Fails when the SQLite the shipped image runs on is older than the floor this
# codebase's SQLite-dependent guarantees were established against.
#
# Phase 1 review 1 (docs/autopilot/reviews/phase-1-review-1.md, finding 2)
# found the gap this guards: the image used to link Debian bookworm's system
# libsqlite3 (3.40.1), several query-planner releases behind everywhere the
# code is developed and tested, and the only symptom was
# tests/test_search.py::test_search_reads_the_index_and_never_scans_a_source_table
# failing inside `make docker-test` with a query plan nobody had changed.
# D-045 ruled option (a): the image moved to a `trixie` base (3.46.1).
#
# A floor, not an exact match (D-047). The three environments cannot share one
# version and never will: a developer's macOS Python, the autopilot sandbox's
# Linux Python and the image's Debian libsqlite3 are packaged independently, so
# requiring equality is a check that can only ever fail. What actually has to
# hold is that the image is not *older* than the engine the guarantees were
# established against -- the FTS5 query-planner shape ADR 0007's test asserts,
# and the WAL/busy_timeout behaviour ADR 0001 depends on.
#
# MINIMUM is the oldest version the in-image suite is known to pass on, proven
# by running it rather than by reading a changelog: 3.46.1 passes all 258
# backend tests, 3.40.1 fails the query-plan assertion. Raise it only alongside
# evidence that the new floor is required, and record why.
#
# Needs a Docker socket, so -- like the rest of the host half of the split gate
# (brief §3.4, sandbox/README.md) -- it cannot run inside the autopilot sandbox.
#
# Usage: scripts/check-sqlite-version.sh <image>
set -euo pipefail
cd "$(dirname "$0")/.."

IMAGE="${1:?Usage: $0 <image>}"
MINIMUM="3.46.1"

dev_version="$(cd backend && uv run python -c 'import sqlite3; print(sqlite3.sqlite_version)')"
image_version="$(docker run --rm --entrypoint python "$IMAGE" -c 'import sqlite3; print(sqlite3.sqlite_version)')"

# sort -V orders version strings; the minimum sorting first means the image is
# at or above it.
oldest="$(printf '%s\n%s\n' "$MINIMUM" "$image_version" | sort -V | head -1)"
if [ "$oldest" != "$MINIMUM" ]; then
  echo "FAIL: ${IMAGE} ships SQLite ${image_version}, older than the ${MINIMUM} floor."
  echo "  image:                                 ${image_version}"
  echo "  floor (in-image suite proven to pass): ${MINIMUM}"
  echo "  this host (uv run python, backend/):   ${dev_version}"
  echo "See docs/autopilot/DECISIONS.md D-045 and D-047."
  exit 1
fi

echo "sqlite version  ok (image ${image_version} >= ${MINIMUM} floor; this host ${dev_version})"
