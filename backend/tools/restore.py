"""Restore a `VACUUM INTO` snapshot over the live database (`make restore`).

Stop the application before running this: `app/backup.restore_backup` deletes
the WAL sidecar files and overwrites `app.db` in place, which a running
process must not race with.

Uploads come back with it (R.5): any blob the live tree is missing is copied
from the snapshot directory's mirror, because a restored row pointing at a
file the volume has lost answers a download with 404.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.backup import RestoreTargetMismatch, restore_backup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "backup_path", type=Path, help="Path to a snapshot produced by `make backup`"
    )
    parser.add_argument(
        "--allow-foreign-snapshot",
        action="store_true",
        help=(
            "restore a snapshot that does not come from this database's own "
            "backup directory (`make restore FOREIGN=1`)"
        ),
    )
    args = parser.parse_args()

    try:
        database_path = restore_backup(
            args.backup_path, allow_foreign_snapshot=args.allow_foreign_snapshot
        )
    except RestoreTargetMismatch as mismatch:
        # Not a traceback: the message is the operator's instructions, and
        # this path exists because the silent version of this failure shipped
        # (R.1c, D-214).
        print(mismatch, file=sys.stderr)
        return 2

    # The absolute path, because the relative one is what made the defect
    # invisible: "Restored ... to app.db" reads as the app's database.
    print(f"Restored {args.backup_path} to {database_path.resolve()}.")
    print("Uploads: any file missing from the live tree was copied back from the mirror.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
