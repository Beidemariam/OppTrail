"""Take a `VACUUM INTO` snapshot of the live database (ADR 0011, `make backup`).

Safe to run at any time, including against a database the app is currently
serving traffic from -- see `app/backup.py` for why.
"""

from __future__ import annotations

from app.backup import attachment_mirror, backup_dir, create_backup, mirror_attachments


def main() -> int:
    destination = create_backup()
    # `create_backup` has already mirrored the blobs; this second call reports
    # what a *subsequent* one would copy, which is zero — so the line below is
    # a statement about the snapshot that was just taken rather than a guess.
    mirror_attachments()
    blobs = sum(1 for path in attachment_mirror().glob("*/*") if path.is_file())
    print(f"Backed up to {destination} (kept in {backup_dir()}).")
    print(f"Uploads mirrored: {blobs} file(s) in {attachment_mirror()}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
