"""Restore a `VACUUM INTO` snapshot over the live database (`make restore`).

Stop the application before running this: `app/backup.restore_backup` deletes
the WAL sidecar files and overwrites `app.db` in place, which a running
process must not race with.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.backup import restore_backup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "backup_path", type=Path, help="Path to a snapshot produced by `make backup`"
    )
    args = parser.parse_args()

    database_path = restore_backup(args.backup_path)
    print(f"Restored {args.backup_path} to {database_path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
