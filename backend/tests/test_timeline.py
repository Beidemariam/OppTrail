from fastapi.testclient import TestClient

from app.database import db_connection


def signup(client: TestClient, email: str, name: str) -> dict:
    response = client.post(
        "/api/auth/signup",
        json={"email": email, "password": "password123", "name": name},
    )
    assert response.status_code == 201
    return response.json()["user"]


def login(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 200


def create_opportunity(client: TestClient) -> dict:
    response = client.post(
        "/api/opportunities",
        json={
            "name": "Expansion",
            "account_name": "Acme",
            "value": "25000",
            "currency": "USD",
            "stage": "Prospecting",
            "expected_close_date": "2026-10-15",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_entry(
    client: TestClient,
    opportunity_id: int,
    title: str = "Discovery call",
    body: str = "Budget discussed",
    entry_type: str = "call",
    event_timestamp: str = "2026-09-01T10:00:00",
) -> dict:
    response = client.post(
        f"/api/opportunities/{opportunity_id}/timeline",
        json={
            "type": entry_type,
            "title": title,
            "body": body,
            "event_timestamp": event_timestamp,
        },
    )
    assert response.status_code == 201
    return response.json()


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


def test_entry_note_comment_crud_and_note_versions(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])

    note = client.post(
        f"/api/timeline/{entry['id']}/notes",
        json={"body": "Follow up with pricing details"},
    )
    assert note.status_code == 201
    note_id = note.json()["id"]

    comment = client.post(
        f"/api/notes/{note_id}/comments",
        json={"body": "I can help with procurement context"},
    )
    assert comment.status_code == 201
    comment_id = comment.json()["id"]

    edited_note = client.patch(
        f"/api/notes/{note_id}",
        json={"body": "Follow up with pricing and procurement details"},
    )
    assert edited_note.status_code == 200
    assert edited_note.json()["edited"] is True

    versions = client.get(f"/api/notes/{note_id}/versions")
    assert versions.status_code == 200
    assert [version["version_number"] for version in versions.json()] == [1, 2]

    updated_entry = client.patch(
        f"/api/timeline/{entry['id']}",
        json={"title": "Updated discovery call", "type": "meeting"},
    )
    assert updated_entry.status_code == 200
    assert updated_entry.json()["title"] == "Updated discovery call"

    timeline = client.get(f"/api/opportunities/{opportunity['id']}/timeline")
    assert timeline.status_code == 200
    manual_entry = next(
        item for item in timeline.json()["entries"] if item["id"] == entry["id"]
    )
    assert manual_entry["notes"][0]["comments"][0]["id"] == comment_id

    assert client.delete(f"/api/comments/{comment_id}").status_code == 204
    assert client.delete(f"/api/notes/{note_id}").status_code == 204
    assert client.delete(f"/api/timeline/{entry['id']}").status_code == 204

    timeline_after_delete = client.get(f"/api/opportunities/{opportunity['id']}/timeline")
    assert timeline_after_delete.status_code == 200
    assert [entry["title"] for entry in timeline_after_delete.json()["entries"]] == [
        "Opportunity created"
    ]


def test_timeline_filters_keyword_type_date_and_author(client: TestClient) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    call = create_entry(
        client,
        opportunity["id"],
        title="Discovery call",
        body="Budget approved",
        entry_type="call",
        event_timestamp="2026-09-01T10:00:00",
    )
    create_entry(
        client,
        opportunity["id"],
        title="Proposal email",
        body="Sent standard proposal",
        entry_type="email",
        event_timestamp="2026-09-10T10:00:00",
    )
    note = client.post(
        f"/api/timeline/{call['id']}/notes",
        json={"body": "Legal team has questions"},
    )
    assert note.status_code == 201

    keyword = client.get(f"/api/opportunities/{opportunity['id']}/timeline?q=legal")
    assert [entry["title"] for entry in keyword.json()["entries"]] == ["Discovery call"]

    entry_type = client.get(f"/api/opportunities/{opportunity['id']}/timeline?type=email")
    assert [entry["title"] for entry in entry_type.json()["entries"]] == ["Proposal email"]

    date_range = client.get(
        f"/api/opportunities/{opportunity['id']}/timeline"
        "?from=2026-09-05T00:00:00&to=2026-09-30T23:59:59"
    )
    assert [entry["title"] for entry in date_range.json()["entries"]] == [
        "Proposal email"
    ]

    author = client.get(
        f"/api/opportunities/{opportunity['id']}/timeline?author_id={owner['id']}"
    )
    assert sorted(entry["title"] for entry in author.json()["entries"]) == [
        "Discovery call",
        "Opportunity created",
        "Proposal email",
    ]


def test_deleting_entry_soft_deletes_related_notes_and_comments(
    client: TestClient,
) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    note = client.post(
        f"/api/timeline/{entry['id']}/notes",
        json={"body": "Entry-related note"},
    ).json()
    comment = client.post(
        f"/api/notes/{note['id']}/comments",
        json={"body": "Entry-related comment"},
    ).json()

    deleted = client.delete(f"/api/timeline/{entry['id']}")
    assert deleted.status_code == 204

    with db_connection() as connection:
        row = connection.execute(
            """
            SELECT
                timeline_entries.deleted_at AS entry_deleted_at,
                notes.deleted_at AS note_deleted_at,
                comments.deleted_at AS comment_deleted_at
            FROM timeline_entries
            JOIN notes ON notes.entry_id = timeline_entries.id
            JOIN comments ON comments.note_id = notes.id
            WHERE timeline_entries.id = ?
                AND notes.id = ?
                AND comments.id = ?
            """,
            (entry["id"], note["id"], comment["id"]),
        ).fetchone()

    assert row["entry_deleted_at"] is not None
    assert row["note_deleted_at"] is not None
    assert row["comment_deleted_at"] is not None


def test_editor_can_write_and_viewer_is_read_only(client: TestClient) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    client.post("/api/auth/logout")

    editor = signup(client, "editor@example.com", "Editor")
    client.post("/api/auth/logout")
    viewer = signup(client, "viewer@example.com", "Viewer")
    client.post("/api/auth/logout")

    share_opportunity(opportunity["id"], editor["id"], owner["id"], "editor")
    share_opportunity(opportunity["id"], viewer["id"], owner["id"], "viewer")

    login(client, "editor@example.com")
    editor_entry = create_entry(client, opportunity["id"], title="Editor meeting")
    client.post("/api/auth/logout")

    login(client, "viewer@example.com")
    readable = client.get(f"/api/opportunities/{opportunity['id']}/timeline")
    assert readable.status_code == 200

    blocked_entry = client.post(
        f"/api/opportunities/{opportunity['id']}/timeline",
        json={
            "type": "call",
            "title": "Viewer call",
            "body": "Should not save",
            "event_timestamp": "2026-09-02T10:00:00",
        },
    )
    assert blocked_entry.status_code == 403

    blocked_note = client.post(
        f"/api/timeline/{editor_entry['id']}/notes",
        json={"body": "Viewer note should not save"},
    )
    assert blocked_note.status_code == 403


def test_comment_delete_is_author_or_owner_only(client: TestClient) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    note = client.post(
        f"/api/timeline/{entry['id']}/notes",
        json={"body": "Owner note"},
    ).json()
    client.post("/api/auth/logout")

    editor = signup(client, "editor@example.com", "Editor")
    client.post("/api/auth/logout")
    other_editor = signup(client, "other-editor@example.com", "Other Editor")
    client.post("/api/auth/logout")
    share_opportunity(opportunity["id"], editor["id"], owner["id"], "editor")
    share_opportunity(opportunity["id"], other_editor["id"], owner["id"], "editor")

    login(client, "editor@example.com")
    comment = client.post(
        f"/api/notes/{note['id']}/comments",
        json={"body": "Editor comment"},
    ).json()
    client.post("/api/auth/logout")

    login(client, "other-editor@example.com")
    blocked = client.delete(f"/api/comments/{comment['id']}")
    assert blocked.status_code == 403
    client.post("/api/auth/logout")

    login(client, "owner@example.com")
    deleted = client.delete(f"/api/comments/{comment['id']}")
    assert deleted.status_code == 204
