"""VACUUM INTO backups and their restore, database and uploads (ADR 0011).

`VACUUM INTO` writes a consistent snapshot to a new file without locking out
writers -- unlike copying `app.db` directly, which can capture a torn WAL
checkpoint -- so this is safe to run against the live database. ADR 0011 also
requires the restore half to be "written and actually exercised", which is
what `tests/test_backup.py::test_restore_recovers_data_written_after_a_backup`
does: back up, write more data, restore, and assert the write is gone and the
backed-up state is back.

**Uploads are part of a snapshot from milestone R.5**, which is the other half
of ADR 0011 item 2 ("plus a copy of `/data/attachments`"). A database restored
without them answers a download with a 404 for a row that says the file is
there, which is the one inconsistency this app's own code calls out as "a real
state until uploads join the backup story in R.5".

Three things follow from attachments being **content addressed** (ADR 0008),
and they are what make this cheap:

- **A mirror, not a copy per snapshot.** A file's name is its SHA-256, so a
  file never changes and two snapshots that both contain it want the same
  bytes. `backups/attachments/` is one mirror of every blob, and taking a
  snapshot copies in only the digests it does not already hold.
- **Nothing in the mirror is ever pruned**, even when the database snapshots
  are. Deleting an attachment in the app is soft and undoable and never
  removes the file (**D-149**), so a kept snapshot can reference any digest
  that has ever existed; a prune predicate safe against that would have to
  read every retained snapshot. Blobs are small here and the rule "keep
  them" is one nobody can get wrong.
- **A restore puts back what is missing and overwrites nothing.** Identical
  digests are identical bytes, so a file already present is already correct.
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .database import sqlite_path_from_url
from .settings import settings
from .time_utils import to_canonical
from .uploads import attachments_dir

BACKUP_FILENAME_PREFIX = "app-"
BACKUP_FILENAME_SUFFIX = ".db"
# Colon-free so the filename is valid on every target filesystem; still
# sortable lexicographically like every other canonical timestamp in the app.
# Microsecond resolution avoids two backups taken inside the same wall-clock
# second (e.g. a retention test, or a human running `make backup` twice in a
# row) colliding on one filename and silently overwriting each other.
FILENAME_TIMESTAMP_FORMAT = "%Y%m%dT%H%M%S%fZ"


def backup_dir() -> Path:
    if settings.backup_dir:
        return Path(settings.backup_dir).expanduser()
    return sqlite_path_from_url(settings.database_url).parent / "backups"


def _backup_files(target_dir: Path) -> list[Path]:
    # Fixed-width timestamp in the filename sorts oldest-to-newest as strings.
    return sorted(target_dir.glob(f"{BACKUP_FILENAME_PREFIX}*{BACKUP_FILENAME_SUFFIX}"))


#: Where the blob mirror lives inside the backup directory.
ATTACHMENT_MIRROR_NAME = "attachments"


def attachment_mirror(destination_dir: Path | None = None) -> Path:
    return (destination_dir or backup_dir()) / ATTACHMENT_MIRROR_NAME


def mirror_attachments(destination_dir: Path | None = None) -> int:
    """Copy any blob the mirror does not already hold, and report how many.

    Content addressing is what makes "already holds it" sound: the name *is*
    the digest, so a file that is there is the right file. Copied through a
    temporary name and renamed, so an interrupted backup cannot leave a
    half-written blob under a digest that promises its contents.
    """
    source_root = attachments_dir()
    if not source_root.is_dir():
        return 0

    mirror_root = attachment_mirror(destination_dir)
    copied = 0
    for blob in sorted(source_root.glob("*/*")):
        if not blob.is_file():
            continue
        target = mirror_root / blob.parent.name / blob.name
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(f"{target.name}.partial")
        shutil.copyfile(blob, partial)
        partial.replace(target)
        copied += 1
    return copied


def create_backup(destination_dir: Path | None = None) -> Path:
    target_dir = destination_dir or backup_dir()
    target_dir.mkdir(parents=True, exist_ok=True)

    source_path = sqlite_path_from_url(settings.database_url)
    stamp = datetime.now(UTC).strftime(FILENAME_TIMESTAMP_FORMAT)
    destination_path = target_dir / f"{BACKUP_FILENAME_PREFIX}{stamp}{BACKUP_FILENAME_SUFFIX}"

    connection = sqlite3.connect(source_path)
    try:
        connection.execute("VACUUM INTO ?", (str(destination_path),))
    finally:
        connection.close()

    # After the snapshot, not before: a blob written between the two is
    # mirrored but unreferenced, which is harmless, while the reverse order
    # would snapshot a row whose file had not been mirrored yet (R.5).
    mirror_attachments(target_dir)

    _prune_old_backups(target_dir)
    return destination_path


def _prune_old_backups(target_dir: Path) -> None:
    """Prune database snapshots only; the blob mirror is never pruned (R.5).

    An attachment's row is soft-deleted and restorable and its file is never
    removed (**D-149**), so any retained snapshot may reference any digest
    that has ever existed. A prune rule safe against that would have to open
    every kept snapshot and union their digests — machinery for a directory
    that holds a few megabytes.
    """
    backups = _backup_files(target_dir)
    excess_count = len(backups) - settings.backup_retention_count
    for stale in backups[:excess_count]:
        stale.unlink()


def latest_backup_at(destination_dir: Path | None = None) -> str | None:
    """The newest snapshot's own timestamp, read from its filename.

    A file in this directory that *looks* like a snapshot but carries
    something else where the timestamp goes is skipped rather than raised on.
    `/api/health` reads this, and a hand-named copy left beside the real
    snapshots — which is a thing an operator does — used to take the probe out
    with a 500 (found by doing exactly that: `app-pre-R1-<stamp>.db`). A
    health endpoint that reports a disk problem must not itself be the
    problem.
    """
    target_dir = destination_dir or backup_dir()
    if not target_dir.is_dir():
        return None
    for candidate in reversed(_backup_files(target_dir)):
        stamp_text = candidate.name.removeprefix(BACKUP_FILENAME_PREFIX).removesuffix(
            BACKUP_FILENAME_SUFFIX
        )
        try:
            parsed = datetime.strptime(stamp_text, FILENAME_TIMESTAMP_FORMAT)
        except ValueError:
            continue
        return to_canonical(parsed.replace(tzinfo=UTC))
    return None


def restore_backup(backup_path: Path) -> Path:
    """Restore a snapshot over the live database file.

    The application must not be running against this database while this
    executes: it deletes the WAL sidecar files outright (stale WAL frames
    checked against a swapped-out main file are not safe to replay) and then
    overwrites `app.db` in place. `make restore` documents this as an offline
    operation; there is no in-app route that calls this.
    """
    if not backup_path.is_file():
        raise FileNotFoundError(f"Backup file not found: {backup_path}")

    database_path = sqlite_path_from_url(settings.database_url)
    for sidecar_suffix in ("-wal", "-shm"):
        sidecar = database_path.with_name(database_path.name + sidecar_suffix)
        sidecar.unlink(missing_ok=True)
    shutil.copyfile(backup_path, database_path)
    restore_attachments(backup_path.parent)
    return database_path


def restore_attachments(source_dir: Path | None = None) -> int:
    """Put back any blob the live tree is missing, and report how many (R.5).

    The direction that matters: a restored database row referring to a file
    the volume has lost answers a download with 404 — the inconsistency ADR
    0011 item 2's "plus a copy of `/data/attachments`" exists to prevent. A
    digest already present is already correct, so nothing here overwrites.
    """
    mirror_root = attachment_mirror(source_dir)
    if not mirror_root.is_dir():
        return 0

    target_root = attachments_dir()
    restored = 0
    for blob in sorted(mirror_root.glob("*/*")):
        if not blob.is_file() or blob.name.endswith(".partial"):
            continue
        target = target_root / blob.parent.name / blob.name
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(blob, target)
        restored += 1
    return restored
