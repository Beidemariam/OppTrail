"""`/api/health` reports substance (ADR 0011, milestone 1.6), not just "ok" --
schema version, database writability, and the last successful backup -- so an
operator can tell a running container apart from a stuck one without opening
a shell.
"""

import os
import stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.backup import create_backup
from app.settings import settings


def test_health_reports_schema_version_and_writability(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert isinstance(body["schema_version"], str) and body["schema_version"]
    assert body["database_writable"] is True


def test_health_last_backup_at_reflects_the_newest_snapshot(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "backup_dir", str(tmp_path / "backups"))

    assert client.get("/api/health").json()["last_backup_at"] is None

    create_backup()

    reported = client.get("/api/health").json()["last_backup_at"]
    assert reported is not None
    assert reported.endswith("Z")


def test_health_reports_unwritable_when_the_database_file_is_read_only(
    client: TestClient, tmp_path: Path
) -> None:
    # WAL mode (ADR 0001) means a write can land in the `-wal` sidecar without
    # ever touching the main file's bytes, so all three -- main file, `-wal`
    # and the containing directory, which a write needs to be able to create
    # a fresh `-wal`/`-shm` pair in -- have to be read-only to actually force
    # `BEGIN IMMEDIATE` to fail.
    read_only_paths = [tmp_path, tmp_path / "test.db", tmp_path / "test.db-wal"]
    original_modes = [path.stat().st_mode for path in read_only_paths if path.exists()]
    existing_paths = [path for path in read_only_paths if path.exists()]
    for path in existing_paths:
        os.chmod(path, stat.S_IRUSR | stat.S_IXUSR)
    try:
        body = client.get("/api/health").json()
    finally:
        for path, mode in zip(existing_paths, original_modes, strict=True):
            os.chmod(path, mode)

    assert body["status"] == "ok"
    assert body["database_writable"] is False
