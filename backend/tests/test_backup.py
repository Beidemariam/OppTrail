"""`VACUUM INTO` backups and their restore (ADR 0011, milestone 1.6).

ADR 0011 requires the restore half to be "written and actually exercised" --
an untested backup is not a backup -- so
`test_restore_recovers_data_written_after_a_backup` drives the real sequence:
back up, write more data, restore, and check the write is gone rather than
merely asserting a file was produced.
"""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.backup import create_backup, latest_backup_at, restore_backup
from app.settings import settings


def signup(client: TestClient, email: str = "owner@example.com") -> dict:
    response = client.post(
        "/api/v2/auth/signup",
        json={"email": email, "password": "password123", "name": "Owner"},
    )
    assert response.status_code == 201
    return response.json()["user"]


def create_opportunity(client: TestClient, name: str = "Expansion") -> dict:
    response = client.post(
        "/api/v2/opportunities",
        json={
            "name": name,
            "account_name": "Acme",
            "value": "25000",
            "currency": "USD",
            "stage": "Prospecting",
            "expected_close_date": "2026-10-15",
        },
    )
    assert response.status_code == 201
    return response.json()


def opportunity_names(database_path: Path) -> list[str]:
    connection = sqlite3.connect(database_path)
    try:
        rows = connection.execute("SELECT name FROM opportunities ORDER BY id").fetchall()
        return [row[0] for row in rows]
    finally:
        connection.close()


def test_backup_snapshot_contains_the_live_data(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "backup_dir", str(tmp_path / "backups"))
    signup(client)
    create_opportunity(client, name="Expansion")

    destination = create_backup()

    assert destination.is_file()
    assert opportunity_names(destination) == ["Expansion"]


def test_latest_backup_at_reports_none_then_a_canonical_timestamp(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "backup_dir", str(tmp_path / "backups"))
    signup(client)

    assert latest_backup_at() is None

    (tmp_path / "backups").mkdir()
    assert latest_backup_at() is None  # directory exists, but nothing in it yet

    create_backup()

    reported = latest_backup_at()
    assert reported is not None
    assert reported.endswith("Z")
    assert "T" in reported
    assert ":" in reported


def test_old_backups_are_pruned_beyond_the_retention_count(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "backup_dir", str(tmp_path / "backups"))
    monkeypatch.setattr(settings, "backup_retention_count", 2)
    signup(client)

    paths = [create_backup() for _ in range(4)]

    remaining = sorted((tmp_path / "backups").glob("app-*.db"))
    assert len(remaining) == 2
    # The two newest survive; the two oldest are gone.
    assert remaining == sorted(paths[-2:])
    for stale in paths[:2]:
        assert not stale.exists()


def test_restore_recovers_data_written_after_a_backup(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "backup_dir", str(tmp_path / "backups"))
    signup(client)
    create_opportunity(client, name="Before backup")

    snapshot = create_backup()

    create_opportunity(client, name="After backup")
    database_path = tmp_path / "test.db"
    assert opportunity_names(database_path) == ["Before backup", "After backup"]

    restore_backup(snapshot)

    assert opportunity_names(database_path) == ["Before backup"]


def test_restore_raises_for_a_missing_backup_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        restore_backup(tmp_path / "does-not-exist.db")


def test_a_hand_named_file_beside_the_snapshots_does_not_take_out_the_probe(
    tmp_path: Path,
) -> None:
    """Found by doing it: a copy named `app-pre-R1-<stamp>.db`, left in the
    backup directory before a risky deploy, made `/api/health` answer 500 —
    the probe that exists to report a disk problem became one (R.1)."""
    (tmp_path / "app-20261013T041025757147Z.db").write_bytes(b"")
    (tmp_path / "app-pre-R1-20261013T110251Z.db").write_bytes(b"")

    assert latest_backup_at(tmp_path) == "2026-10-13T04:10:25Z"


def test_a_directory_of_nothing_parseable_answers_none(tmp_path: Path) -> None:
    (tmp_path / "app-notes.db").write_bytes(b"")

    assert latest_backup_at(tmp_path) is None
