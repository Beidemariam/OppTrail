#!/usr/bin/env bash
# Human-only: accept a reviewed autopilot phase.
# Fast-forwards main to autopilot/phase-<ID> and tags phase-<ID>-accepted.
# Usage: scripts/autopilot-accept.sh <phase-id>     e.g. F, 1, 2 ... 6, R
#        PUSH=1 scripts/autopilot-accept.sh 1        also pushes main and the tag
set -euo pipefail
cd "$(dirname "$0")/.."

# Human-only by construction: the autopilot agent runs non-interactively, so it
# cannot reach the tagging path below even if it ignores the brief.
[ -t 0 ] || { echo "$0 requires an interactive terminal." >&2; exit 1; }

PHASE="${1:?Usage: $0 <phase-id>}"
BRANCH="autopilot/phase-${PHASE}"
TAG="phase-${PHASE}-accepted"

git rev-parse -q --verify "refs/heads/${BRANCH}" >/dev/null || { echo "No branch ${BRANCH}."; exit 1; }
git rev-parse -q --verify "refs/tags/${TAG}" >/dev/null && { echo "${TAG} already exists."; exit 1; }
[ -z "$(git status --porcelain --untracked-files=no)" ] || { echo "Uncommitted changes to tracked files. Commit or stash first."; exit 1; }

status="$(git show "${BRANCH}:docs/autopilot/PROGRESS.md" 2>/dev/null | head -n1 || true)"
if [ "$status" != "STATUS: AWAITING_REVIEW phase=${PHASE}" ]; then
  echo "Branch status is '${status:-missing}', not AWAITING_REVIEW for phase ${PHASE}."
  read -r -p "Accept anyway? [y/N] " ans; [ "${ans:-N}" = "y" ] || exit 1
fi

echo "Commits to be accepted into main:"
git log --oneline "main..${BRANCH}"
read -r -p "Fast-forward main to ${BRANCH} and tag ${TAG}? [y/N] " ans
[ "${ans:-N}" = "y" ] || { echo "Cancelled."; exit 1; }

git checkout main
if ! git merge --ff-only "${BRANCH}"; then
  echo "Fast-forward failed: main has commits not on ${BRANCH}."
  echo "Rebase the branch onto main (git checkout ${BRANCH} && git rebase main), re-run 'make check', then accept again."
  exit 1
fi
git tag -a "${TAG}" -m "Phase ${PHASE} accepted"

if [ "${PUSH:-0}" = "1" ]; then
  git push origin main "${TAG}"
fi

echo "Phase ${PHASE} accepted. Run scripts/autopilot.sh to start the next phase."