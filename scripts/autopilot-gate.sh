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

# D-030(a). Until this step existed, both halves of the split gate ran the test
# suites only under Linux -- the sandbox's own container -- so nothing ever
# exercised them on the reviewer's platform. F.7's WeasyPrint failure reached
# the human directly instead of failing a gate. Run first: it is far cheaper
# than the image build below, so a platform-specific break fails fast.
# The receipt names a commit, so the suite has to run against that commit's
# tree. The image build below is immune -- it archives the branch -- but this
# step runs in the working tree, so refuse unless the two agree.
if [ "$(git rev-parse HEAD)" != "$SHA" ] || [ -n "$(git status --porcelain)" ]; then
  echo "The host suite runs in your working tree, so it must be a clean"
  echo "checkout of ${BRANCH} or the receipt would name a commit it never ran."
  echo "  HEAD:        $(git rev-parse --short HEAD)"
  echo "  ${BRANCH}: ${SHA:0:12}"
  [ -n "$(git status --porcelain)" ] && echo "  working tree: dirty"
  exit 1
fi

echo "--- host test suite ($(uname -sm)) ---"
make test-host

# Build the application image from the phase branch without disturbing your
# working tree, by piping a git archive of that commit as the build context.
echo "--- docker build ---"
git archive "${BRANCH}" | docker build -t "$IMAGE" -

# D-046: names an environment divergence directly, by version number, instead
# of waiting for it to surface as an unrelated test failure downstream (which
# is exactly how phase-1-review-1.md's finding 2 was first found). Run right
# after the build, before the suite that finding actually broke, so the cause
# is on screen before the symptom is.
echo "--- sqlite version agreement (host vs. image) ---"
./scripts/check-sqlite-version.sh "$IMAGE"

# ROADMAP.md Phase 1's "backend suite inside the image". The working tree is
# already a clean checkout of this exact commit (checked above), so this can
# build straight from it rather than archiving a second time.
echo "--- backend suite inside the image ---"
make docker-test

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
verified=host-pytest,host-vitest,docker-build,sqlite-version-agreement,docker-test,health,csrf,signup,opportunity-create,timeline,pdf-export,frontend-served
at=$(date -u +%FT%TZ)
RECEIPT

echo
echo "Host gate PASSED. Receipt: ${GATE_DIR}/${SHA}"
echo "You can now run: scripts/autopilot-accept.sh ${PHASE}"
