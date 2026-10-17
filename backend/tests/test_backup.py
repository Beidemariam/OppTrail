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
from test_attachments import PDF, upload
from test_timeline import create_entry

from app.backup import (
    attachment_mirror,
    create_backup,
    latest_backup_at,
    mirror_attachments,
    restore_backup,
)
from app.settings import settings
from app.uploads import attachments_dir, resolve_stored_path


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


def test_a_snapshot_carries_the_uploads_and_a_restore_puts_them_back(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR 0011 item 2's other half, built in R.5: "plus a copy of
    `/data/attachments`".

    The failure this prevents is specific and was a documented real state
    until now — a restored database row says a file is there and the download
    answers 404, because the row came back and the bytes did not. So the test
    loses the live blob on purpose, which is what a lost volume looks like
    from the application's side.
    """
    destination = tmp_path / "backups"
    monkeypatch.setattr(settings, "backup_dir", str(destination))

    signup(client)
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"], "Proposal sent")
    attachment = upload(client, entry["id"])

    snapshot = create_backup()
    mirrored = sorted(path.name for path in attachment_mirror().glob("*/*") if path.is_file())
    assert mirrored == [attachment["sha256"]], mirrored

    # The volume loses the blob but keeps the database: the row is still there
    # and the bytes are gone, which is the inconsistency to repair.
    live = resolve_stored_path(attachments_dir(), attachment["sha256"])
    live.unlink()
    assert client.get(f"/api/v2/attachments/{attachment['id']}/download").status_code == 404

    restore_backup(snapshot)

    assert live.is_file()
    recovered = client.get(f"/api/v2/attachments/{attachment['id']}/download")
    assert recovered.status_code == 200
    assert recovered.content == PDF


def test_mirroring_the_same_upload_twice_copies_it_once(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What content addressing buys: a file's name is its digest, so a blob the
    mirror already holds is a blob it holds correctly, and the second snapshot
    copies nothing."""
    monkeypatch.setattr(settings, "backup_dir", str(tmp_path / "backups"))

    signup(client)
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"], "Proposal sent")
    upload(client, entry["id"])

    assert mirror_attachments() == 1
    assert mirror_attachments() == 0


def test_the_blob_mirror_is_not_pruned_with_the_snapshots(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Retention applies to database snapshots only (R.5): an attachment's
    delete is soft and never removes the file (D-149), so any retained
    snapshot may reference any digest that has ever existed."""
    monkeypatch.setattr(settings, "backup_dir", str(tmp_path / "backups"))
    monkeypatch.setattr(settings, "backup_retention_count", 1)

    signup(client)
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"], "Proposal sent")
    attachment = upload(client, entry["id"])

    create_backup()
    create_backup()

    assert len(list(Path(settings.backup_dir).glob("app-*.db"))) == 1
    assert (attachment_mirror() / attachment["sha256"][:2] / attachment["sha256"]).is_file()
