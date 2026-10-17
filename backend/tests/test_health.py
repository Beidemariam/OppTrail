"""The three operations endpoints, and the different questions they answer.

`/api/health` reports substance (ADR 0011, milestone 1.6), not just "ok" --
schema version, database writability, the last successful backup and the
newest run of each scheduled job -- so an operator can tell a running
container apart from a stuck one without opening a shell.

`/healthz` and `/readyz` joined it in milestone R.4 (**D-203**, scheduled by
D-094). The last two tests here are the reason they are separate endpoints:
with the database unwritable, the deployment is **not ready** and the process
is still **alive**, and restarting it would not empty a disk.
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


def test_liveness_does_no_io_at_all(client: TestClient) -> None:
    """What an orchestrator restarts a container for. It must not depend on
    the database: a liveness probe that reads a full disk turns a degraded
    deployment into a restart loop."""
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_answers_with_a_status_code(client: TestClient) -> None:
    """A `HEALTHCHECK` reads the exit code of its command and nothing else, so
    this is the probe it can be pointed at."""
    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def read_only(paths: list[Path]):
    """Make a SQLite database genuinely unwritable, WAL and all."""
    existing = [path for path in paths if path.exists()]
    modes = [path.stat().st_mode for path in existing]
    for path in existing:
        os.chmod(path, stat.S_IRUSR | stat.S_IXUSR)
    return existing, modes


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


def test_readiness_fails_while_liveness_holds_on_an_unwritable_database(
    client: TestClient, tmp_path: Path
) -> None:
    """The split, demonstrated: this deployment cannot serve a write and the
    process is fine. ADR 0011 item 4 asks for the healthcheck against
    `/api/health`, which answers **200** here by design — pointing it there
    would report healthy on exactly this failure, which is why R.4 points it
    at `/readyz` instead (**D-203**)."""
    existing, modes = read_only([tmp_path, tmp_path / "test.db", tmp_path / "test.db-wal"])
    try:
        ready = client.get("/readyz")
        alive = client.get("/healthz")
        rich = client.get("/api/health")
    finally:
        for path, mode in zip(existing, modes, strict=True):
            os.chmod(path, mode)

    assert ready.status_code == 503
    assert ready.json() == {"status": "unavailable"}
    assert alive.status_code == 200
    assert rich.status_code == 200
    assert rich.json()["database_writable"] is False
