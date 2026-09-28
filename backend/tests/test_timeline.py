from datetime import UTC, datetime, timedelta

import httpx
from fastapi.testclient import TestClient

from app.database import db_connection


def days_ago(days: int) -> str:
    """Timestamp relative to now, so no assertion depends on today's date."""
    return (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def signup(client: TestClient, email: str, name: str) -> dict:
    response = client.post(
        "/api/v2/auth/signup",
        json={"email": email, "password": "password123", "name": name},
    )
    assert response.status_code == 201
    return response.json()["user"]


def login(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/v2/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 200


def create_opportunity(client: TestClient) -> dict:
    response = client.post(
        "/api/v2/opportunities",
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
        f"/api/v2/opportunities/{opportunity_id}/timeline",
        json={
            "type": entry_type,
            "title": title,
            "body": body,
            "event_timestamp": event_timestamp,
        },
    )
    assert response.status_code == 201
    return response.json()


def edit_note(client: TestClient, note_id: int, body: str) -> httpx.Response:
    """PATCH a note, echoing the `updated_at` the server currently holds.

    ADR 0003's edit guard (milestone 3.4) makes `updated_at` part of every note
    edit, and the frontend echoes the value it has on screen. A test that means
    to exercise the *edit* reads the current one first, so it is never the
    thing under test; `tests/test_events.py` is where a deliberately stale
    value goes.
    """
    with db_connection() as connection:
        row = connection.execute(
            "SELECT updated_at FROM notes WHERE id = ?",
            (note_id,),
        ).fetchone()
    return client.patch(
        f"/api/v2/notes/{note_id}",
        json={"body": body, "updated_at": row["updated_at"] if row else ""},
    )


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
        f"/api/v2/timeline/{entry['id']}/notes",
        json={"body": "Follow up with pricing details"},
    )
    assert note.status_code == 201
    note_id = note.json()["id"]

    comment = client.post(
        f"/api/v2/notes/{note_id}/comments",
        json={"body": "I can help with procurement context"},
    )
    assert comment.status_code == 201
    comment_id = comment.json()["id"]

    edited_note = edit_note(client, note_id, "Follow up with pricing and procurement details")
    assert edited_note.status_code == 200
    assert edited_note.json()["edited"] is True

    versions = client.get(f"/api/v2/notes/{note_id}/versions")
    assert versions.status_code == 200
    assert [version["version_number"] for version in versions.json()["items"]] == [1, 2]

    updated_entry = client.patch(
        f"/api/v2/timeline/{entry['id']}",
        json={"title": "Updated discovery call", "type": "meeting"},
    )
    assert updated_entry.status_code == 200
    assert updated_entry.json()["title"] == "Updated discovery call"

    timeline = client.get(f"/api/v2/opportunities/{opportunity['id']}/timeline")
    assert timeline.status_code == 200
    manual_entry = next(item for item in timeline.json()["items"] if item["id"] == entry["id"])
    assert manual_entry["notes"][0]["comments"][0]["id"] == comment_id

    assert client.delete(f"/api/v2/comments/{comment_id}").status_code == 204
    assert client.delete(f"/api/v2/notes/{note_id}").status_code == 204
    assert client.delete(f"/api/v2/timeline/{entry['id']}").status_code == 204

    timeline_after_delete = client.get(f"/api/v2/opportunities/{opportunity['id']}/timeline")
    assert timeline_after_delete.status_code == 200
    assert [entry["title"] for entry in timeline_after_delete.json()["items"]] == [
        "Opportunity created"
    ]


def test_timeline_filters_keyword_type_date_and_author(client: TestClient) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    # The auto-generated "Opportunity created" entry is stamped with the current
    # time, so every window here is anchored to now rather than a fixed date.
    call = create_entry(
        client,
        opportunity["id"],
        title="Discovery call",
        body="Budget approved",
        entry_type="call",
        event_timestamp=days_ago(60),
    )
    create_entry(
        client,
        opportunity["id"],
        title="Proposal email",
        body="Sent standard proposal",
        entry_type="email",
        event_timestamp=days_ago(30),
    )
    note = client.post(
        f"/api/v2/timeline/{call['id']}/notes",
        json={"body": "Legal team has questions"},
    )
    assert note.status_code == 201

    keyword = client.get(f"/api/v2/opportunities/{opportunity['id']}/timeline?q=legal")
    assert [entry["title"] for entry in keyword.json()["items"]] == ["Discovery call"]

    entry_type = client.get(f"/api/v2/opportunities/{opportunity['id']}/timeline?type=email")
    assert [entry["title"] for entry in entry_type.json()["items"]] == ["Proposal email"]

    date_range = client.get(
        f"/api/v2/opportunities/{opportunity['id']}/timeline?from={days_ago(45)}&to={days_ago(15)}"
    )
    assert [entry["title"] for entry in date_range.json()["items"]] == ["Proposal email"]

    author = client.get(
        f"/api/v2/opportunities/{opportunity['id']}/timeline?author_id={owner['id']}"
    )
    assert sorted(entry["title"] for entry in author.json()["items"]) == [
        "Discovery call",
        "Opportunity created",
        "Proposal email",
    ]


def test_the_three_new_entry_types_are_accepted_and_filterable(client: TestClient) -> None:
    """Milestone 2.6: `site_visit`, `objection` and `competitor_intel` join the
    eight the MVP shipped -- additive, so the eight already covered elsewhere
    in this file are untouched.
    """
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    create_entry(
        client,
        opportunity["id"],
        title="Toured the warehouse",
        entry_type="site_visit",
        event_timestamp=days_ago(5),
    )
    create_entry(
        client,
        opportunity["id"],
        title="Pricing pushback",
        entry_type="objection",
        event_timestamp=days_ago(4),
    )
    create_entry(
        client,
        opportunity["id"],
        title="Evaluating a rival vendor",
        entry_type="competitor_intel",
        event_timestamp=days_ago(3),
    )

    for entry_type, title in (
        ("site_visit", "Toured the warehouse"),
        ("objection", "Pricing pushback"),
        ("competitor_intel", "Evaluating a rival vendor"),
    ):
        response = client.get(
            f"/api/v2/opportunities/{opportunity['id']}/timeline?type={entry_type}"
        )
        assert [entry["title"] for entry in response.json()["items"]] == [title]


def test_an_unrecognized_entry_type_is_rejected(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)

    rejected = client.post(
        f"/api/v2/opportunities/{opportunity['id']}/timeline",
        json={
            "type": "carrier_pigeon",
            "title": "Not a real type",
            "event_timestamp": "2026-09-01T10:00:00",
        },
    )

    assert rejected.status_code == 422


def test_timeline_order_direction(client: TestClient) -> None:
    """D-051: the reader chooses oldest- or newest-first; `order` defaults to
    the existing behaviour (oldest-first) so a client that never sends it sees
    no change.
    """
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    create_entry(
        client,
        opportunity["id"],
        title="Discovery call",
        event_timestamp=days_ago(60),
    )
    create_entry(
        client,
        opportunity["id"],
        title="Proposal email",
        event_timestamp=days_ago(30),
    )

    def titles(query: str) -> list[str]:
        response = client.get(f"/api/v2/opportunities/{opportunity['id']}/timeline{query}")
        return [entry["title"] for entry in response.json()["items"]]

    assert titles("") == titles("?order=asc")
    assert titles("?order=desc") == list(reversed(titles("?order=asc")))


def test_deleting_entry_soft_deletes_related_notes_and_comments(
    client: TestClient,
) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    note = client.post(
        f"/api/v2/timeline/{entry['id']}/notes",
        json={"body": "Entry-related note"},
    ).json()
    comment = client.post(
        f"/api/v2/notes/{note['id']}/comments",
        json={"body": "Entry-related comment"},
    ).json()

    deleted = client.delete(f"/api/v2/timeline/{entry['id']}")
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
    client.post("/api/v2/auth/logout")

    editor = signup(client, "editor@example.com", "Editor")
    client.post("/api/v2/auth/logout")
    viewer = signup(client, "viewer@example.com", "Viewer")
    client.post("/api/v2/auth/logout")

    share_opportunity(opportunity["id"], editor["id"], owner["id"], "editor")
    share_opportunity(opportunity["id"], viewer["id"], owner["id"], "viewer")

    login(client, "editor@example.com")
    editor_entry = create_entry(client, opportunity["id"], title="Editor meeting")
    client.post("/api/v2/auth/logout")

    login(client, "viewer@example.com")
    readable = client.get(f"/api/v2/opportunities/{opportunity['id']}/timeline")
    assert readable.status_code == 200

    blocked_entry = client.post(
        f"/api/v2/opportunities/{opportunity['id']}/timeline",
        json={
            "type": "call",
            "title": "Viewer call",
            "body": "Should not save",
            "event_timestamp": "2026-09-02T10:00:00",
        },
    )
    assert blocked_entry.status_code == 403

    blocked_note = client.post(
        f"/api/v2/timeline/{editor_entry['id']}/notes",
        json={"body": "Viewer note should not save"},
    )
    assert blocked_note.status_code == 403


def test_comment_delete_is_author_or_owner_only(client: TestClient) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    note = client.post(
        f"/api/v2/timeline/{entry['id']}/notes",
        json={"body": "Owner note"},
    ).json()
    client.post("/api/v2/auth/logout")

    editor = signup(client, "editor@example.com", "Editor")
    client.post("/api/v2/auth/logout")
    other_editor = signup(client, "other-editor@example.com", "Other Editor")
    client.post("/api/v2/auth/logout")
    share_opportunity(opportunity["id"], editor["id"], owner["id"], "editor")
    share_opportunity(opportunity["id"], other_editor["id"], owner["id"], "editor")

    login(client, "editor@example.com")
    comment = client.post(
        f"/api/v2/notes/{note['id']}/comments",
        json={"body": "Editor comment"},
    ).json()
    client.post("/api/v2/auth/logout")

    login(client, "other-editor@example.com")
    blocked = client.delete(f"/api/v2/comments/{comment['id']}")
    assert blocked.status_code == 403
    client.post("/api/v2/auth/logout")

    login(client, "owner@example.com")
    deleted = client.delete(f"/api/v2/comments/{comment['id']}")
    assert deleted.status_code == 204


def test_editor_cannot_change_another_users_note_or_entry(client: TestClient) -> None:
    """Editing a colleague's record is author-or-owner, exactly like deleting.

    This test previously asserted that an editor could PATCH a colleague's
    note. That expectation is retired under the human ruling recorded in
    DECISIONS.md D-005, which overruled the permissive reading and rewrote
    `AGENTS.md`'s permissions model: an editor who may not remove a
    colleague's record may not rewrite it either.
    """
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"], title="Owner call")
    note = client.post(
        f"/api/v2/timeline/{entry['id']}/notes",
        json={"body": "Owner note"},
    ).json()
    client.post("/api/v2/auth/logout")

    editor = signup(client, "editor@example.com", "Editor")
    client.post("/api/v2/auth/logout")
    share_opportunity(opportunity["id"], editor["id"], owner["id"], "editor")

    login(client, "editor@example.com")
    assert client.delete(f"/api/v2/notes/{note['id']}").status_code == 403
    assert client.delete(f"/api/v2/timeline/{entry['id']}").status_code == 403
    assert edit_note(client, note["id"], "Editor edit").status_code == 403
    assert (
        client.patch(f"/api/v2/timeline/{entry['id']}", json={"title": "Editor edit"}).status_code
        == 403
    )

    # An editor still owns everything they create themselves.
    own_entry = create_entry(client, opportunity["id"], title="Editor call")
    own_note = client.post(
        f"/api/v2/timeline/{own_entry['id']}/notes",
        json={"body": "Editor note"},
    ).json()
    assert (
        client.patch(f"/api/v2/timeline/{own_entry['id']}", json={"title": "Edited"}).status_code
        == 200
    )
    assert edit_note(client, own_note["id"], "Edited").status_code == 200
    assert client.delete(f"/api/v2/timeline/{own_entry['id']}").status_code == 204
    client.post("/api/v2/auth/logout")

    # The owner can change or remove anything on their own opportunity.
    login(client, "owner@example.com")
    assert edit_note(client, note["id"], "Owner edit").status_code == 200
    assert (
        client.patch(f"/api/v2/timeline/{entry['id']}", json={"title": "Owner edit"}).status_code
        == 200
    )
    assert client.delete(f"/api/v2/notes/{note['id']}").status_code == 204
    assert client.delete(f"/api/v2/timeline/{entry['id']}").status_code == 204


def test_owner_can_edit_an_editors_entry_and_note(client: TestClient) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    client.post("/api/v2/auth/logout")

    editor = signup(client, "editor@example.com", "Editor")
    client.post("/api/v2/auth/logout")
    share_opportunity(opportunity["id"], editor["id"], owner["id"], "editor")

    login(client, "editor@example.com")
    entry = create_entry(client, opportunity["id"], title="Editor call")
    note = client.post(
        f"/api/v2/timeline/{entry['id']}/notes",
        json={"body": "Editor note"},
    ).json()
    client.post("/api/v2/auth/logout")

    login(client, "owner@example.com")
    edited_entry = client.patch(f"/api/v2/timeline/{entry['id']}", json={"title": "Owner retitled"})
    assert edited_entry.status_code == 200
    assert edited_entry.json()["title"] == "Owner retitled"

    edited_note = edit_note(client, note["id"], "Owner rewrote this")
    assert edited_note.status_code == 200
    assert edited_note.json()["body"] == "Owner rewrote this"


def test_deletions_are_recorded_in_the_audit_log(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    note = client.post(
        f"/api/v2/timeline/{entry['id']}/notes",
        json={"body": "Owner note"},
    ).json()
    comment = client.post(
        f"/api/v2/notes/{note['id']}/comments",
        json={"body": "Owner comment"},
    ).json()

    assert client.delete(f"/api/v2/comments/{comment['id']}").status_code == 204
    assert client.delete(f"/api/v2/notes/{note['id']}").status_code == 204
    assert client.delete(f"/api/v2/timeline/{entry['id']}").status_code == 204

    audit = client.get(f"/api/v2/opportunities/{opportunity['id']}/audit-log")
    assert audit.status_code == 200
    actions = [row["action"] for row in audit.json()["items"]]
    assert actions == ["comment_deleted", "note_deleted", "timeline_entry_deleted"]
    detail = next(
        row["detail"] for row in audit.json()["items"] if row["action"] == "timeline_entry_deleted"
    )
    assert detail["entry_id"] == entry["id"]

    assert client.delete(f"/api/v2/opportunities/{opportunity['id']}").status_code == 204
    with db_connection() as connection:
        deleted = connection.execute(
            """
            SELECT action FROM audit_log_entries
            WHERE opportunity_id = ? AND action = 'opportunity_deleted'
            """,
            (opportunity["id"],),
        ).fetchone()
    assert deleted is not None


def test_timestamps_are_canonical_utc_and_sort_chronologically(
    client: TestClient,
) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)

    # The "Opportunity created" system entry is stamped now; this user entry is
    # earlier on the same day, so it must sort first.
    earlier_today = (datetime.now(UTC) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    create_entry(client, opportunity["id"], title="Earlier today", event_timestamp=earlier_today)

    entries = client.get(f"/api/v2/opportunities/{opportunity['id']}/timeline").json()["items"]
    stamps = [entry["event_timestamp"] for entry in entries]
    assert all(len(stamp) == 20 and stamp.endswith("Z") for stamp in stamps)
    assert stamps == sorted(stamps)
    assert [entry["title"] for entry in entries] == [
        "Earlier today",
        "Opportunity created",
    ]

    # A filter from the start of today must include the system entry, which the
    # old space-separated format sorted below any "T"-separated bound.
    start_of_day = datetime.now(UTC).strftime("%Y-%m-%dT00:00:00Z")
    filtered = client.get(
        f"/api/v2/opportunities/{opportunity['id']}/timeline?from={start_of_day}"
    ).json()["items"]
    assert "Opportunity created" in [entry["title"] for entry in filtered]


def test_client_timestamps_are_normalized_to_utc(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)

    naive = create_entry(
        client, opportunity["id"], title="No seconds", event_timestamp="2026-09-01T10:00"
    )
    assert naive["event_timestamp"] == "2026-09-01T10:00:00Z"

    offset = create_entry(
        client,
        opportunity["id"],
        title="With offset",
        event_timestamp="2026-09-01T12:00:00+02:00",
    )
    assert offset["event_timestamp"] == "2026-09-01T10:00:00Z"


def test_invalid_timestamps_are_rejected_and_the_dashboard_stays_up(
    client: TestClient,
) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)

    rejected = client.post(
        f"/api/v2/opportunities/{opportunity['id']}/timeline",
        json={"type": "call", "title": "Bad", "event_timestamp": "not-a-timestamp"},
    )
    assert rejected.status_code == 422

    rejected_date = client.post(
        f"/api/v2/opportunities/{opportunity['id']}/timeline",
        json={
            "type": "call",
            "title": "Bad follow up",
            "event_timestamp": "2026-09-01T10:00:00Z",
            "follow_up_date": "31-12-2026",
        },
    )
    assert rejected_date.status_code == 422

    # A rejected write must not be able to take the dashboard down for anyone.
    assert client.get("/api/v2/opportunities").status_code == 200
