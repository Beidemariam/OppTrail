"""Undo: the restore half of the soft-delete design (milestone 2.4b).

`docs/FEATURES.md` §12 asks for undo that is "a real `deleted_at = NULL`, not a
re-create". These tests hold the two properties that makes non-trivial:

- A restore puts back exactly what its own delete took, identified by the
  single `deleted_at` stamp the cascade wrote — so a note deleted separately
  beforehand stays deleted when its entry comes back.
- The row keeps its id, so every reference to it (a note's `entry_id`, a search
  index rowid, an audit detail) still resolves to the same record.
"""

from fastapi.testclient import TestClient

from app.database import db_connection


def signup(client: TestClient, email: str, name: str) -> dict:
    response = client.post(
        "/api/v2/auth/signup",
        json={"email": email, "password": "password123", "name": name},
    )
    assert response.status_code == 201
    return response.json()["user"]


def login(client: TestClient, email: str) -> None:
    assert (
        client.post(
            "/api/v2/auth/login",
            json={"email": email, "password": "password123"},
        ).status_code
        == 200
    )


def create_opportunity(client: TestClient, name: str = "Expansion") -> dict:
    response = client.post(
        "/api/v2/opportunities",
        json={
            "name": name,
            "account_name": "Acme",
            "value": "25000",
            "currency": "USD",
            "stage": "Prospecting",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_entry(client: TestClient, opportunity_id: int, title: str = "Discovery call") -> dict:
    response = client.post(
        f"/api/v2/opportunities/{opportunity_id}/timeline",
        json={
            "type": "call",
            "title": title,
            "body": "Budget discussed",
            "event_timestamp": "2026-09-01T10:00:00",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_note(client: TestClient, entry_id: int, body: str = "Follow up in a week") -> dict:
    response = client.post(f"/api/v2/timeline/{entry_id}/notes", json={"body": body})
    assert response.status_code == 201
    return response.json()


def create_comment(client: TestClient, note_id: int, body: str = "Agreed") -> dict:
    response = client.post(f"/api/v2/notes/{note_id}/comments", json={"body": body})
    assert response.status_code == 201
    return response.json()


def backdate_delete(table: str, row_id: int) -> None:
    """Move one row's delete stamp an hour into the past.

    A delete that happened earlier is the case these tests are about, and
    `utc_now()` has one-second resolution, so a prior delete made through the
    API microseconds earlier would share the cascade's stamp (DECISIONS.md
    D-067 records that one-second window as an accepted limitation). Backdating
    makes the fixture mean what it says: this was deleted a while ago.
    """
    with db_connection() as connection:
        connection.execute(
            f"UPDATE {table} SET deleted_at = datetime(deleted_at, '-1 hour') WHERE id = ?",
            (row_id,),
        )
        connection.commit()


def share_opportunity(opportunity_id: int, user_id: int, invited_by: int, role: str) -> None:
    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO opportunity_shares (opportunity_id, user_id, invited_by, role)
            VALUES (?, ?, ?, ?)
            """,
            (opportunity_id, user_id, invited_by, role),
        )
        connection.commit()


def timeline(client: TestClient, opportunity_id: int) -> list[dict]:
    response = client.get(f"/api/v2/opportunities/{opportunity_id}/timeline")
    assert response.status_code == 200
    entries: list[dict] = response.json()["items"]
    return entries


def find_entry(client: TestClient, opportunity_id: int, entry_id: int) -> dict | None:
    return next(
        (entry for entry in timeline(client, opportunity_id) if entry["id"] == entry_id),
        None,
    )


def audit_actions(client: TestClient, opportunity_id: int) -> list[str]:
    response = client.get(f"/api/v2/opportunities/{opportunity_id}/audit-log")
    assert response.status_code == 200
    return [row["action"] for row in response.json()["items"]]


def test_restoring_an_entry_brings_back_the_notes_that_delete_took(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    kept = create_note(client, entry["id"], "Still wanted")
    comment = create_comment(client, kept["id"])

    # Deleted on its own first, an hour of work before the entry went. The
    # entry's restore must not resurrect it.
    separately_deleted = create_note(client, entry["id"], "Already gone")
    assert client.delete(f"/api/v2/notes/{separately_deleted['id']}").status_code == 204
    backdate_delete("notes", separately_deleted["id"])

    assert client.delete(f"/api/v2/timeline/{entry['id']}").status_code == 204
    assert find_entry(client, opportunity["id"], entry["id"]) is None

    assert client.post(f"/api/v2/timeline/{entry['id']}/restore").status_code == 204, (
        "the author restores their own entry"
    )

    restored = find_entry(client, opportunity["id"], entry["id"])
    assert restored is not None
    assert restored["id"] == entry["id"], "undo keeps the id; it is not a re-create"
    note_ids = [note["id"] for note in restored["notes"]]
    assert note_ids == [kept["id"]]
    assert [item["id"] for item in restored["notes"][0]["comments"]] == [comment["id"]]


def test_restoring_a_note_brings_back_its_comments(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    note = create_note(client, entry["id"])
    comment = create_comment(client, note["id"])

    assert client.delete(f"/api/v2/notes/{note['id']}").status_code == 204
    assert timeline(client, opportunity["id"])[-1]["notes"] == []

    assert client.post(f"/api/v2/notes/{note['id']}/restore").status_code == 204

    notes = find_entry(client, opportunity["id"], entry["id"])["notes"]  # type: ignore[index]
    assert [item["id"] for item in notes] == [note["id"]]
    assert [item["id"] for item in notes[0]["comments"]] == [comment["id"]]


def test_restoring_a_comment_puts_it_back_under_its_note(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    note = create_note(client, entry["id"])
    comment = create_comment(client, note["id"])

    assert client.delete(f"/api/v2/comments/{comment['id']}").status_code == 204
    assert client.post(f"/api/v2/comments/{comment['id']}/restore").status_code == 204

    restored = find_entry(client, opportunity["id"], entry["id"])
    assert restored is not None
    assert [item["id"] for item in restored["notes"][0]["comments"]] == [comment["id"]]


def test_restoring_an_opportunity_brings_back_its_timeline_and_shares(
    client: TestClient,
) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    editor = signup(client, "editor@example.com", "Editor")
    login(client, "owner@example.com")
    opportunity = create_opportunity(client)
    share_opportunity(opportunity["id"], editor["id"], owner["id"], "editor")
    entry = create_entry(client, opportunity["id"])
    note = create_note(client, entry["id"])

    assert client.delete(f"/api/v2/opportunities/{opportunity['id']}").status_code == 204
    assert client.get(f"/api/v2/opportunities/{opportunity['id']}").status_code == 404

    assert client.post(f"/api/v2/opportunities/{opportunity['id']}/restore").status_code == 204

    assert client.get(f"/api/v2/opportunities/{opportunity['id']}").status_code == 200
    restored = find_entry(client, opportunity["id"], entry["id"])
    assert restored is not None
    assert [item["id"] for item in restored["notes"]] == [note["id"]]

    # The share came back with it, so the colleague can read the record again.
    login(client, "editor@example.com")
    assert client.get(f"/api/v2/opportunities/{opportunity['id']}").status_code == 200


def test_restoring_an_opportunity_leaves_an_earlier_delete_alone(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    create_entry(client, opportunity["id"], "Kept")
    dropped = create_entry(client, opportunity["id"], "Dropped earlier")
    assert client.delete(f"/api/v2/timeline/{dropped['id']}").status_code == 204
    backdate_delete("timeline_entries", dropped["id"])

    assert client.delete(f"/api/v2/opportunities/{opportunity['id']}").status_code == 204
    assert client.post(f"/api/v2/opportunities/{opportunity['id']}/restore").status_code == 204

    titles = [entry["title"] for entry in timeline(client, opportunity["id"])]
    assert "Kept" in titles
    assert "Dropped earlier" not in titles


def test_restore_is_recorded_in_the_audit_log(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    note = create_note(client, entry["id"])
    comment = create_comment(client, note["id"])

    assert client.delete(f"/api/v2/comments/{comment['id']}").status_code == 204
    assert client.post(f"/api/v2/comments/{comment['id']}/restore").status_code == 204
    assert client.delete(f"/api/v2/notes/{note['id']}").status_code == 204
    assert client.post(f"/api/v2/notes/{note['id']}/restore").status_code == 204
    assert client.delete(f"/api/v2/timeline/{entry['id']}").status_code == 204
    assert client.post(f"/api/v2/timeline/{entry['id']}/restore").status_code == 204

    # Undo adds a row rather than removing the delete's: the log is the
    # sequence of what happened, not the current state.
    assert audit_actions(client, opportunity["id"]) == [
        "comment_deleted",
        "comment_restored",
        "note_deleted",
        "note_restored",
        "timeline_entry_deleted",
        "timeline_entry_restored",
    ]

    detail = client.get(f"/api/v2/opportunities/{opportunity['id']}/audit-log").json()["items"][-1][
        "detail"
    ]
    assert detail["entry_id"] == entry["id"]
    assert detail["title"] == entry["title"]


def test_restored_content_is_searchable_again(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"], "Procurement objection")

    def hits() -> int:
        response = client.get("/api/v2/search?q=procurement")
        assert response.status_code == 200
        return len(response.json()["items"])

    assert hits() == 1
    assert client.delete(f"/api/v2/timeline/{entry['id']}").status_code == 204
    assert hits() == 0, "a deleted entry leaves the index"
    assert client.post(f"/api/v2/timeline/{entry['id']}/restore").status_code == 204
    assert hits() == 1, "and the restore trigger puts it back"


def test_restoring_twice_is_not_found_the_second_time(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])

    assert client.delete(f"/api/v2/timeline/{entry['id']}").status_code == 204
    assert client.post(f"/api/v2/timeline/{entry['id']}/restore").status_code == 204

    # Nothing is deleted any more, so there is nothing to restore. Same answer
    # as an entry that was never deleted, and as one that never existed.
    assert client.post(f"/api/v2/timeline/{entry['id']}/restore").status_code == 404
    assert client.post(f"/api/v2/timeline/{entry['id'] + 500}/restore").status_code == 404


def test_a_child_cannot_be_restored_while_its_parent_is_deleted(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    note = create_note(client, entry["id"])

    assert client.delete(f"/api/v2/timeline/{entry['id']}").status_code == 204

    # Restoring the note alone would put a row back into a tree nobody can
    # read, so the only way back is through the entry's own restore.
    assert client.post(f"/api/v2/notes/{note['id']}/restore").status_code == 404
    assert client.post(f"/api/v2/timeline/{entry['id']}/restore").status_code == 204
    assert client.post(f"/api/v2/notes/{note['id']}/restore").status_code == 404


def test_restore_follows_the_same_rule_as_delete(client: TestClient) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    editor = signup(client, "editor@example.com", "Editor")
    viewer = signup(client, "viewer@example.com", "Viewer")
    signup(client, "outsider@example.com", "Outsider")
    login(client, "owner@example.com")
    opportunity = create_opportunity(client)
    share_opportunity(opportunity["id"], editor["id"], owner["id"], "editor")
    share_opportunity(opportunity["id"], viewer["id"], owner["id"], "viewer")

    # An entry the editor wrote, deleted by the editor.
    login(client, "editor@example.com")
    entry = create_entry(client, opportunity["id"], "Editor's call")
    assert client.delete(f"/api/v2/timeline/{entry['id']}").status_code == 204

    login(client, "outsider@example.com")
    assert client.post(f"/api/v2/timeline/{entry['id']}/restore").status_code == 404

    login(client, "viewer@example.com")
    assert client.post(f"/api/v2/timeline/{entry['id']}/restore").status_code == 403

    # The owner may restore anyone's item, exactly as they may delete it
    # (DECISIONS.md D-005).
    login(client, "owner@example.com")
    assert client.post(f"/api/v2/timeline/{entry['id']}/restore").status_code == 204

    # A colleague's item is not the editor's to restore, either.
    owned_entry = create_entry(client, opportunity["id"], "Owner's call")
    assert client.delete(f"/api/v2/timeline/{owned_entry['id']}").status_code == 204
    login(client, "editor@example.com")
    assert client.post(f"/api/v2/timeline/{owned_entry['id']}/restore").status_code == 403


def test_only_the_owner_can_restore_an_opportunity(client: TestClient) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    editor = signup(client, "editor@example.com", "Editor")
    login(client, "owner@example.com")
    opportunity = create_opportunity(client)
    share_opportunity(opportunity["id"], editor["id"], owner["id"], "editor")
    assert client.delete(f"/api/v2/opportunities/{opportunity['id']}").status_code == 204

    # A deleted record leaks nothing, not even to the colleague who could read
    # it an hour ago: 404, not 403.
    login(client, "editor@example.com")
    assert client.post(f"/api/v2/opportunities/{opportunity['id']}/restore").status_code == 404

    login(client, "owner@example.com")
    assert client.post(f"/api/v2/opportunities/{opportunity['id']}/restore").status_code == 204


def test_restore_needs_a_session(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    assert client.delete(f"/api/v2/timeline/{entry['id']}").status_code == 204
    assert client.post("/api/v2/auth/logout").status_code == 200

    response = client.post(f"/api/v2/timeline/{entry['id']}/restore")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized", "v2 error envelope"
