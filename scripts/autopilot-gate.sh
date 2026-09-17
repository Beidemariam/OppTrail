#!/usr/bin/env bash
# Host-side half of the quality gate (docs/autopilot-brief.md 3.4).
#
# The sandbox has no Docker socket by design (sandbox/README.md), so the agent
# cannot run "Docker build + smoke test". This script is that step, run by you
# on the host before accepting a phase.
#
# It writes a receipt keyed to the exact commit it tested, into a directory that
# is never mounted into the sandbox, so the agent cannot forge one.
# scripts/autopilot-accept.sh requires a matching receipt.
#
# Usage: scripts/autopilot-gate.sh <phase-id>
set -euo pipefail
cd "$(dirname "$0")/.."

PHASE="${1:?Usage: $0 <phase-id>}"
BRANCH="autopilot/phase-${PHASE}"
GATE_DIR="${AUTOPILOT_GATE_DIR:-${HOME}/.opptrail-autopilot/gate}"
IMAGE="opptrail-gate-candidate:phase-${PHASE}"
CONTAINER="opptrail-gate-smoke-$$"
PORT="${GATE_PORT:-8899}"

git rev-parse -q --verify "refs/heads/${BRANCH}" >/dev/null \
  || { echo "No branch ${BRANCH}."; exit 1; }
SHA="$(git rev-parse "${BRANCH}")"
mkdir -p "$GATE_DIR"

echo "=== Host gate for phase ${PHASE} at ${SHA:0:12} ==="

# Build the application image from the phase branch without disturbing your
# working tree, by piping a git archive of that commit as the build context.
echo "--- docker build ---"
git archive "${BRANCH}" | docker build -t "$IMAGE" -

# One definition of "the image works", shared with `make docker-smoke` and CI.
# It exercises session auth, CSRF, a write, the auto-generated timeline entry,
# the WeasyPrint PDF path (the reason this step cannot run in the sandbox), and
# same-origin delivery of the frontend.
echo "--- smoke test ---"
SMOKE_PORT="$PORT" ./scripts/docker-smoke.sh "$IMAGE" "$CONTAINER"

cat > "${GATE_DIR}/${SHA}" <<RECEIPT
phase=${PHASE}
branch=${BRANCH}
commit=${SHA}
image=${IMAGE}
host=$(uname -srm)
docker=$(docker --version)
verified=docker-build,health,csrf,signup,opportunity-create,timeline,pdf-export,frontend-served
at=$(date -u +%FT%TZ)
RECEIPT

echo
echo "Host gate PASSED. Receipt: ${GATE_DIR}/${SHA}"
echo "You can now run: scripts/autopilot-accept.sh ${PHASE}"
