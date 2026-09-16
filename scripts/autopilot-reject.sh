#!/usr/bin/env bash
# Human-only: reject a reviewed autopilot phase with feedback.
# Records feedback on autopilot/phase-<ID> and sets STATUS: REWORK so the next
# autopilot run addresses it before returning to AWAITING_REVIEW.
# Usage: scripts/autopilot-reject.sh <phase-id> <feedback-file.md>
set -euo pipefail
cd "$(dirname "$0")/.."

PHASE="${1:?Usage: $0 <phase-id> <feedback-file.md>}"
FEEDBACK="${2:?Usage: $0 <phase-id> <feedback-file.md>}"
BRANCH="autopilot/phase-${PHASE}"
PROGRESS="docs/autopilot/PROGRESS.md"

[ -f "$FEEDBACK" ] || { echo "Feedback file not found: $FEEDBACK"; exit 1; }
FEEDBACK_ABS="$(cd "$(dirname "$FEEDBACK")" && pwd)/$(basename "$FEEDBACK")"
git rev-parse -q --verify "refs/heads/${BRANCH}" >/dev/null || { echo "No branch ${BRANCH}."; exit 1; }
[ -z "$(git status --porcelain --untracked-files=no)" ] || { echo "Uncommitted changes to tracked files. Commit or stash first."; exit 1; }

git checkout "${BRANCH}"
mkdir -p docs/autopilot/reviews
n=1; while [ -f "docs/autopilot/reviews/phase-${PHASE}-review-${n}.md" ]; do n=$((n + 1)); done
OUT="docs/autopilot/reviews/phase-${PHASE}-review-${n}.md"

{
  echo "# Phase ${PHASE} — Review ${n}"
  echo
  echo "Decision: REJECT"
  echo "Date: $(date -u +%F)"
  echo
  echo "## Feedback (address every item before returning to AWAITING_REVIEW)"
  echo
  cat "$FEEDBACK_ABS"
} > "$OUT"

# Replace the status line portably (works with macOS and GNU tooling).
perl -pi -e "s/^STATUS: .*/STATUS: REWORK phase=${PHASE}/ if \$. == 1" "$PROGRESS"

git add "$OUT" "$PROGRESS"
git commit -m "chore(autopilot): phase ${PHASE} review ${n} — rework requested"

echo "Rework requested for phase ${PHASE} (${OUT}). Run scripts/autopilot.sh to continue."