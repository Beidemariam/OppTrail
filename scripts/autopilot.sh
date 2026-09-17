#!/usr/bin/env bash
# Phase-gated autopilot runner.
# Runs one Claude Code session per milestone until the current phase reaches
# AWAITING_REVIEW, is BLOCKED, or stops making progress.
# Run INSIDE a container/VM that mounts only this repo.
set -euo pipefail
cd "$(dirname "$0")/.."

MAX_RUNS="${MAX_RUNS:-40}"
MAX_TURNS="${MAX_TURNS:-250}"
# Unset means "whatever the CLI defaults to". Set it to put a specific model on
# a milestone -- e.g. MODEL=opus for the Alembic baseline (F.4) or the frontend
# decomposition (Phase 2), which are the two hardest things in the plan to
# recover from. Accepts an alias (opus/sonnet/haiku) or a full model id.
MODEL="${MODEL:-}"
LOG_DIR="${LOG_DIR:-../opptrail-autopilot-logs}"   # outside the repo
PROGRESS="docs/autopilot/PROGRESS.md"
mkdir -p "$LOG_DIR"

status_line() { [ -f "$PROGRESS" ] && head -n1 "$PROGRESS" || echo "STATUS: NONE"; }
phase_of()    { sed -n 's/.*phase=\([A-Za-z0-9]*\).*/\1/p' <<<"$1"; }

no_progress=0
for i in $(seq 1 "$MAX_RUNS"); do
  line="$(status_line)"
  phase="$(phase_of "$line")"

  case "$line" in
    "STATUS: AWAITING_REVIEW"*)
      if git rev-parse -q --verify "refs/tags/phase-${phase}-accepted" >/dev/null; then
        if [ "$phase" = "R" ]; then
          echo "Phase R accepted — autopilot finished."; exit 0
        fi
        echo "Phase ${phase} accepted — starting next phase."
      else
        echo
        echo "Phase ${phase} is ready for review."
        echo "  Review packet: docs/autopilot/reviews/phase-${phase}-summary.md  (on branch autopilot/phase-${phase})"
        echo "  Accept:  scripts/autopilot-accept.sh ${phase}"
        echo "  Reject:  scripts/autopilot-reject.sh ${phase} path/to/feedback.md"
        exit 0
      fi
      ;;
    "STATUS: BLOCKED"*)
      echo "Phase ${phase} is BLOCKED — see docs/autopilot/BLOCKERS.md."
      echo "Resolve the blocker, then re-run this script."
      # Allow one session to re-check; exit if still blocked afterwards.
      ;;
  esac

  before="$(git rev-parse HEAD):$(status_line)"
  log_file="$LOG_DIR/run-$(date -u +%Y%m%dT%H%M%S).log"
  # The header goes through tee too, so the log records which model produced the
  # commit. Printing it only to the terminal left every run unattributable.
  echo "=== Run $i/$MAX_RUNS — $(date -u +%FT%TZ) — ${line} — requested=${MODEL:-cli-default} ===" | tee "$log_file"

  # An API error mid-response used to abort the whole script through pipefail,
  # losing the attribution footer on exactly the runs that most need it. Record
  # the status instead and let the no-progress counter below decide.
  rc=0
  claude -p "Read docs/autopilot-brief.md in full, then every file in docs/autopilot/ that exists. \
Follow §3.3 exactly: determine the current state, then complete at most one milestone (or the rework items, \
or the end-of-phase review packet), update the state files, commit to the autopilot branch, and exit. \
Never commit to main, merge, push, or create acceptance tags." \
    --dangerously-skip-permissions \
    ${MODEL:+--model "$MODEL"} \
    --max-turns "$MAX_TURNS" \
    --output-format text 2>&1 | tee -a "$log_file" || rc=$?

  # The header can only name what was asked for -- an alias like "opus", or
  # "cli-default" when MODEL is unset, neither of which is a model id. The
  # session transcript names what actually answered. Entries reading
  # "<synthetic>" are the CLI's own error messages, not a model, so skip them.
  transcript="$(ls -t "$HOME"/.claude/projects/*/*.jsonl 2>/dev/null | head -1 || true)"
  served=""
  if [ -n "$transcript" ]; then
    served="$(grep -ho '"model":"[^"]*"' "$transcript" \
      | sed 's/.*:"//; s/"$//' | grep -v '^<' | tail -1 || true)"
  fi
  echo "=== Run $i/$MAX_RUNS — exit=${rc} — served=${served:-unknown} ===" | tee -a "$log_file"
  if [ "$rc" -ne 0 ]; then echo "claude exited ${rc}; see ${log_file}"; fi

  after="$(git rev-parse HEAD):$(status_line)"
  case "$(status_line)" in "STATUS: BLOCKED"*) echo "Still BLOCKED — stopping."; exit 1;; esac

  if [ "$before" = "$after" ]; then
    no_progress=$((no_progress + 1))
    echo "No new commit or status change ($no_progress/3)."
    [ "$no_progress" -ge 3 ] && { echo "Stopping: no progress in 3 runs. Check the latest log."; exit 1; }
  else
    no_progress=0
  fi
done

echo "Reached MAX_RUNS ($MAX_RUNS). Current: $(status_line)"