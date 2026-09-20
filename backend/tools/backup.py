"""Take a `VACUUM INTO` snapshot of the live database (ADR 0011, `make backup`).

Safe to run at any time, including against a database the app is currently
serving traffic from -- see `app/backup.py` for why.
"""

from __future__ import annotations

from app.backup import backup_dir, create_backup


def main() -> int:
    destination = create_backup()
    print(f"Backed up to {destination} (kept in {backup_dir()}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
