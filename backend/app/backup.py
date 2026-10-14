"""VACUUM INTO backups and their restore (ADR 0011).

`VACUUM INTO` writes a consistent snapshot to a new file without locking out
writers -- unlike copying `app.db` directly, which can capture a torn WAL
checkpoint -- so this is safe to run against the live database. ADR 0011 also
requires the restore half to be "written and actually exercised", which is
what `tests/test_backup.py::test_restore_recovers_data_written_after_a_backup`
does: back up, write more data, restore, and assert the write is gone and the
backed-up state is back.
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .database import sqlite_path_from_url
from .settings import settings
from .time_utils import to_canonical

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

    _prune_old_backups(target_dir)
    return destination_path


def _prune_old_backups(target_dir: Path) -> None:
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
    return database_path
