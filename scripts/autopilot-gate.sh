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

cleanup() { docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "=== Host gate for phase ${PHASE} at ${SHA:0:12} ==="

# Build the application image from the phase branch without disturbing your
# working tree, by piping a git archive of that commit as the build context.
echo "--- docker build ---"
git archive "${BRANCH}" | docker build -t "$IMAGE" -

echo "--- start ---"
docker run -d --rm --name "$CONTAINER" -p "${PORT}:8000" \
  -e OPENAI_API_KEY=gate-smoke-test-unused "$IMAGE" >/dev/null

api="http://127.0.0.1:${PORT}"
for _ in $(seq 1 60); do
  curl -fsS "${api}/api/health" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS "${api}/api/health" >/dev/null || { echo "FAIL: health check never passed"; docker logs "$CONTAINER" | tail -30; exit 1; }
echo "health          ok"

# Exercise the real stack end to end: session auth, a write, and the WeasyPrint
# PDF path, which is the reason this step cannot run in the sandbox.
jar="$(mktemp)"; trap 'rm -f "$jar"' RETURN 2>/dev/null || true
user="gate-$(date +%s)@example.com"

curl -fsS -c "$jar" -X POST "${api}/api/auth/signup" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"${user}\",\"password\":\"gate-smoke-pw-123\",\"name\":\"Gate Smoke\"}" >/dev/null
echo "signup          ok"

opp="$(curl -fsS -b "$jar" -X POST "${api}/api/opportunities" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Gate smoke opportunity","account_name":"Acme","stage":"Qualification"}')"
opp_id="$(printf '%s' "$opp" | sed -n 's/.*"id":[ ]*\([0-9]*\).*/\1/p' | head -1)"
[ -n "$opp_id" ] || { echo "FAIL: could not create an opportunity: $opp"; exit 1; }
echo "opportunity     ok (id ${opp_id})"

pdf="$(mktemp)"
curl -fsS -b "$jar" "${api}/api/opportunities/${opp_id}/export/pdf" -o "$pdf"
if [ "$(head -c 4 "$pdf")" = "%PDF" ]; then
  echo "pdf export      ok ($(wc -c < "$pdf" | tr -d ' ') bytes, %PDF verified)"
else
  echo "FAIL: export did not return a PDF"; head -c 200 "$pdf"; rm -f "$pdf"; exit 1
fi
rm -f "$pdf"

# The static frontend must be served from the same origin as the API.
curl -fsS "${api}/" | grep -qi '<html' && echo "frontend        ok" \
  || { echo "FAIL: frontend not served"; exit 1; }

cat > "${GATE_DIR}/${SHA}" <<RECEIPT
phase=${PHASE}
branch=${BRANCH}
commit=${SHA}
image=${IMAGE}
host=$(uname -srm)
docker=$(docker --version)
verified=docker-build,health,signup,opportunity-create,pdf-export,frontend-served
at=$(date -u +%FT%TZ)
RECEIPT

echo
echo "Host gate PASSED. Receipt: ${GATE_DIR}/${SHA}"
echo "You can now run: scripts/autopilot-accept.sh ${PHASE}"
