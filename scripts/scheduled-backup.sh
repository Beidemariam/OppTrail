#!/usr/bin/env bash
# The scheduled snapshot, and the copy off this disk (R.1c, the reviewer's
# choice at the Phase R gate).
#
# Why this exists as a script rather than two lines in a scheduler:
#
# - **`uv` is not on a scheduled job's PATH.** It lives in `~/.local/bin`, which
#   a login shell adds and `launchd` does not. The naive version of this fails
#   with `uv: command not found` every night and you find out at the restore.
# - **The off-box copy is the half this repository cannot do for you.**
#   `backups/` sits on the same volume as the database (`docs/operations.md`),
#   so it protects against a bad write and not against losing the drive.
# - **One command is testable.** `scripts/scheduled-backup.sh` can be run by
#   hand, and what the scheduler runs is what you tested.
set -euo pipefail

REPO="${OPPTRAIL_REPO:-$HOME/Projects/Sales_Opp_Tracker}"
MIRROR="${OPPTRAIL_OFFSITE:-$HOME/Library/Mobile Documents/com~apple~CloudDocs/OppTrail-backups}"
LOG="${OPPTRAIL_BACKUP_LOG:-$HOME/Library/Logs/opptrail-backup.log}"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

# **The script owns its log, not the LaunchAgent.** `launchd` does not expand
# `$HOME` in `StandardOutPath` -- it would create a directory called `$HOME`
# -- so a checked-in plist cannot name a log file without hard-coding one
# machine's home directory. A shell can, so this does, and the plist in
# `scripts/com.opptrail.backup.plist` is portable as committed.
mkdir -p "$(dirname "$LOG")"
exec >> "$LOG" 2>&1

cd "$REPO"
echo "=== $(date -u +%FT%TZ) snapshot ==="

# `make backup` names the deployment's database itself (D-214) and prunes to
# BACKUP_RETENTION_COUNT. Run against the live volume while the app serves:
# `VACUUM INTO` is consistent without locking writers out (ADR 0011).
make backup

# Copy, never delete: the mirror is the thing that survives losing this disk,
# so local retention pruning must not reach through to it. `--ignore-existing`
# keeps a snapshot that has already been copied from being rewritten every
# night -- a snapshot file never changes once written.
#
# **The snapshot is already safe by this point.** If the copy fails, that is
# reported and the script exits non-zero, because a backup you believe is
# offsite and is not is worse than one you know is local-only -- but the
# ordering means a failure here never costs you the snapshot.
echo "=== offsite copy -> ${MIRROR} ==="
mkdir -p "$MIRROR" 2>/dev/null || true
if rsync -a --ignore-existing data/backups/ "$MIRROR/" 2>&1; then
  echo "=== $(date -u +%FT%TZ) done: $(ls -1 "$MIRROR" | wc -l | tr -d ' ') file(s) offsite ==="
else
  cat >&2 <<'BLOCKED'

The snapshot was taken. The copy off this disk was REFUSED.

If that said "Operation not permitted", it is macOS privacy protection and not
a bug: a scheduled job has no access to iCloud Drive, Desktop or Documents
until you grant it. Running this script from Terminal works, because Terminal
already has that access -- which is exactly why this has to be tested the way
the scheduler runs it.

Two ways out:

  1. System Settings -> Privacy & Security -> Full Disk Access -> + -> press
     Cmd+Shift+G and enter /bin/bash. Then:
        launchctl kickstart -k gui/$(id -u)/com.opptrail.backup
     and check this log again.

  2. Point it somewhere unprotected instead, in the LaunchAgent or inline:
        OPPTRAIL_OFFSITE=/Volumes/YourDisk/OppTrail scripts/scheduled-backup.sh

Until one of those, you have local snapshots on a schedule and nothing off
this disk -- which protects you from a bad write and not from losing the drive.
BLOCKED
  exit 1
fi
