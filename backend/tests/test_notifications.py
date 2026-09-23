from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.database import db_connection
from app.notification_service import extract_mentioned_emails


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


def create_entry(client: TestClient, opportunity_id: int) -> dict:
    response = client.post(
        f"/api/v2/opportunities/{opportunity_id}/timeline",
        json={
            "type": "call",
            "title": "Discovery call",
            "body": "Budget discussed",
            "event_timestamp": "2026-09-04T10:00:00",
            "follow_up_date": "2026-09-10",
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


def test_extract_mentioned_emails_deduplicates_case_insensitively() -> None:
    body = "Ping @Viewer@Example.com and @viewer@example.com, plus @owner@example.com."

    assert extract_mentioned_emails(body) == [
        "viewer@example.com",
        "owner@example.com",
    ]


def test_mentions_comments_and_shared_activity_create_notifications(
    client: TestClient,
) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    client.post("/api/v2/auth/logout")

    viewer = signup(client, "viewer@example.com", "Viewer")
    client.post("/api/v2/auth/logout")
    editor = signup(client, "editor@example.com", "Editor")
    client.post("/api/v2/auth/logout")

    share_opportunity(opportunity["id"], viewer["id"], owner["id"], "viewer")
    share_opportunity(opportunity["id"], editor["id"], owner["id"], "editor")

    login(client, "owner@example.com")
    note = client.post(
        f"/api/v2/timeline/{entry['id']}/notes",
        json={"body": "Please review this @viewer@example.com"},
    )
    assert note.status_code == 201
    client.post("/api/v2/auth/logout")

    login(client, "viewer@example.com")
    viewer_notifications = client.get("/api/v2/notifications")
    assert viewer_notifications.status_code == 200
    viewer_types = {notification["type"] for notification in viewer_notifications.json()["items"]}
    assert "mention" in viewer_types
    assert "shared_activity" in viewer_types
    client.post("/api/v2/auth/logout")

    login(client, "editor@example.com")
    comment = client.post(
        f"/api/v2/notes/{note.json()['id']}/comments",
        json={"body": "Legal is aligned @viewer@example.com"},
    )
    assert comment.status_code == 201
    client.post("/api/v2/auth/logout")

    login(client, "owner@example.com")
    owner_notifications = client.get("/api/v2/notifications").json()["items"]
    assert {notification["type"] for notification in owner_notifications} >= {
        "comment",
        "shared_activity",
    }


def test_user_can_mark_only_own_notification_read(client: TestClient) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    client.post("/api/v2/auth/logout")

    viewer = signup(client, "viewer@example.com", "Viewer")
    client.post("/api/v2/auth/logout")
    other = signup(client, "other@example.com", "Other")
    client.post("/api/v2/auth/logout")

    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO notifications (user_id, type, payload)
            VALUES (
                ?,
                'mention',
                '{"opportunity_id": 1, "source_type": "entry", "source_id": 1,
                  "actor_id": 1, "email": "viewer@example.com"}'
            )
            """,
            (viewer["id"],),
        )
        connection.execute(
            """
            INSERT INTO notifications (user_id, type, payload)
            VALUES (
                ?,
                'mention',
                '{"opportunity_id": 1, "source_type": "entry", "source_id": 1,
                  "actor_id": 1, "email": "other@example.com"}'
            )
            """,
            (other["id"],),
        )
        connection.commit()
        other_notification_id = connection.execute(
            "SELECT id FROM notifications WHERE user_id = ?",
            (other["id"],),
        ).fetchone()["id"]

    login(client, "viewer@example.com")
    notifications = client.get("/api/v2/notifications").json()["items"]
    assert len(notifications) == 1

    marked = client.patch(f"/api/v2/notifications/{notifications[0]['id']}/read")
    assert marked.status_code == 200
    assert marked.json()["read_at"] is not None

    # The inbox keeps what has been read (milestone 1.7). v1 answered an
    # unread-only list here, so marking one read made it disappear; that
    # surface went with v1 in 2.9 and `read_at` carries the state instead.
    after = client.get("/api/v2/notifications").json()["items"]
    assert [row["id"] for row in after] == [notifications[0]["id"]]
    assert after[0]["read_at"] == marked.json()["read_at"]

    blocked = client.patch(f"/api/v2/notifications/{other_notification_id}/read")
    assert blocked.status_code == 404
    assert owner["id"] == opportunity["owner_id"]


def test_share_changes_create_notifications_for_shared_user(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    client.post("/api/v2/auth/logout")

    viewer = signup(client, "viewer@example.com", "Viewer")
    client.post("/api/v2/auth/logout")

    login(client, "owner@example.com")
    added = client.post(
        f"/api/v2/opportunities/{opportunity['id']}/shares",
        json={"email": viewer["email"], "role": "viewer"},
    )
    assert added.status_code == 201
    changed = client.patch(
        f"/api/v2/opportunities/{opportunity['id']}/shares/{viewer['id']}",
        json={"role": "editor"},
    )
    assert changed.status_code == 200
    removed = client.delete(f"/api/v2/opportunities/{opportunity['id']}/shares/{viewer['id']}")
    assert removed.status_code == 204
    client.post("/api/v2/auth/logout")

    login(client, "viewer@example.com")
    notification_types = {
        notification["type"] for notification in client.get("/api/v2/notifications").json()["items"]
    }
    assert notification_types >= {
        "share_added",
        "share_role_changed",
        "share_removed",
    }


def test_follow_up_permissions_and_stalled_calculation(client: TestClient) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    client.post("/api/v2/auth/logout")

    viewer = signup(client, "viewer@example.com", "Viewer")
    client.post("/api/v2/auth/logout")
    share_opportunity(opportunity["id"], viewer["id"], owner["id"], "viewer")

    login(client, "viewer@example.com")
    blocked_follow_up = client.patch(
        f"/api/v2/timeline/{entry['id']}",
        json={"follow_up_date": "2026-09-20"},
    )
    assert blocked_follow_up.status_code == 403
    client.post("/api/v2/auth/logout")

    login(client, "owner@example.com")
    updated_follow_up = client.patch(
        f"/api/v2/timeline/{entry['id']}",
        json={"follow_up_date": "2026-09-20"},
    )
    assert updated_follow_up.status_code == 200
    assert updated_follow_up.json()["follow_up_date"] == "2026-09-20"

    old_timestamp = (datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)).isoformat(
        timespec="seconds"
    )
    with db_connection() as connection:
        connection.execute(
            """
            UPDATE timeline_entries
            SET event_timestamp = ?, created_at = ?
            WHERE opportunity_id = ?
            """,
            (old_timestamp, old_timestamp, opportunity["id"]),
        )
        connection.commit()

    stalled = client.get("/api/v2/opportunities").json()["items"][0]
    assert stalled["stalled"] is True

    note = client.post(
        f"/api/v2/timeline/{entry['id']}/notes",
        json={"body": "Fresh follow up"},
    )
    assert note.status_code == 201

    refreshed = client.get("/api/v2/opportunities").json()["items"][0]
    assert refreshed["stalled"] is False
