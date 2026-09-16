"""Invariant: user data is soft-deleted, never removed (brief §2.4).

The guard is a source scan rather than a runtime check because a hard delete is
a thing the code must not *contain*: a `DELETE FROM notes` on a path no test
happens to exercise would still ship. `test_the_guard_detects_a_hard_delete`
runs the same scanner over a file that does contain one, so a broken scanner
cannot pass silently.
"""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.database import db_connection
from app.soft_delete import USER_DATA_TABLES

APP_DIR = Path(__file__).resolve().parent.parent / "app"
HARD_DELETE = re.compile(r"\bDELETE\s+FROM\s+[\"'`\[]?(\w+)", re.IGNORECASE)


def signup(client: TestClient, email: str, name: str) -> None:
    response = client.post(
        "/api/auth/signup",
        json={"email": email, "password": "password123", "name": name},
    )
    assert response.status_code == 201


def hard_deletes(paths: list[Path]) -> list[str]:
    """Every `DELETE FROM <user data table>` in the given sources."""
    found = []
    for path in sorted(paths):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            match = HARD_DELETE.search(line)
            if match and match.group(1).lower() in USER_DATA_TABLES:
                found.append(f"{path.name}:{number}: {line.strip()}")
    return found


def test_invariant_no_hard_deletes_of_user_data() -> None:
    assert hard_deletes(list(APP_DIR.glob("*.py"))) == []


def test_the_guard_detects_a_hard_delete(tmp_path: Path) -> None:
    offender = tmp_path / "routes_bad.py"
    offender.write_text(
        'connection.execute("DELETE FROM notes WHERE id = ?", (note_id,))\n',
        encoding="utf-8",
    )

    assert hard_deletes([offender]) == [
        'routes_bad.py:1: connection.execute("DELETE FROM notes WHERE id = ?", (note_id,))'
    ]


def test_the_guard_allows_session_cleanup(tmp_path: Path) -> None:
    """Sessions are authentication state, not user data, and are really deleted."""
    logout = tmp_path / "auth.py"
    logout.write_text(
        'connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))\n',
        encoding="utf-8",
    )

    assert hard_deletes([logout]) == []


def test_invariant_deleting_an_opportunity_retains_every_row(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    signup(client, "editor@example.com", "Editor")
    client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "password123"},
    )
    opportunity_id = client.post(
        "/api/opportunities",
        json={
            "name": "Expansion",
            "account_name": "Acme",
            "value": "25000",
            "currency": "USD",
            "stage": "Prospecting",
        },
    ).json()["id"]
    assert (
        client.post(
            f"/api/opportunities/{opportunity_id}/shares",
            json={"email": "editor@example.com", "role": "editor"},
        ).status_code
        == 201
    )
    entry_id = client.post(
        f"/api/opportunities/{opportunity_id}/timeline",
        json={
            "type": "call",
            "title": "Discovery call",
            "body": "Budget discussed",
            "event_timestamp": "2026-09-01T10:00:00",
        },
    ).json()["id"]
    note_id = client.post(f"/api/timeline/{entry_id}/notes", json={"body": "Note"}).json()["id"]
    assert (
        client.post(f"/api/notes/{note_id}/comments", json={"body": "Comment"}).status_code == 201
    )

    assert client.delete(f"/api/opportunities/{opportunity_id}").status_code == 204

    with db_connection() as connection:
        for table in (
            "opportunities",
            "opportunity_shares",
            "timeline_entries",
            "notes",
            "comments",
        ):
            rows = connection.execute(f"SELECT deleted_at FROM {table}").fetchall()
            assert rows, f"{table} lost its rows"
            assert all(row["deleted_at"] is not None for row in rows), table
