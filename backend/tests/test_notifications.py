from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.database import db_connection
from app.notification_service import extract_mentioned_emails


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


def create_entry(client: TestClient, opportunity_id: int) -> dict:
    response = client.post(
        f"/api/opportunities/{opportunity_id}/timeline",
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
    client.post("/api/auth/logout")

    viewer = signup(client, "viewer@example.com", "Viewer")
    client.post("/api/auth/logout")
    editor = signup(client, "editor@example.com", "Editor")
    client.post("/api/auth/logout")

    share_opportunity(opportunity["id"], viewer["id"], owner["id"], "viewer")
    share_opportunity(opportunity["id"], editor["id"], owner["id"], "editor")

    login(client, "owner@example.com")
    note = client.post(
        f"/api/timeline/{entry['id']}/notes",
        json={"body": "Please review this @viewer@example.com"},
    )
    assert note.status_code == 201
    client.post("/api/auth/logout")

    login(client, "viewer@example.com")
    viewer_notifications = client.get("/api/notifications")
    assert viewer_notifications.status_code == 200
    viewer_types = {
        notification["type"]
        for notification in viewer_notifications.json()["notifications"]
    }
    assert "mention" in viewer_types
    assert "shared_activity" in viewer_types
    client.post("/api/auth/logout")

    login(client, "editor@example.com")
    comment = client.post(
        f"/api/notes/{note.json()['id']}/comments",
        json={"body": "Legal is aligned @viewer@example.com"},
    )
    assert comment.status_code == 201
    client.post("/api/auth/logout")

    login(client, "owner@example.com")
    owner_notifications = client.get("/api/notifications").json()["notifications"]
    assert {notification["type"] for notification in owner_notifications} >= {
        "comment",
        "shared_activity",
    }


def test_user_can_mark_only_own_notification_read(client: TestClient) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    client.post("/api/auth/logout")

    viewer = signup(client, "viewer@example.com", "Viewer")
    client.post("/api/auth/logout")
    other = signup(client, "other@example.com", "Other")
    client.post("/api/auth/logout")

    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO notifications (user_id, type, payload)
            VALUES (?, 'mention', '{"opportunity_id": 1}')
            """,
            (viewer["id"],),
        )
        connection.execute(
            """
            INSERT INTO notifications (user_id, type, payload)
            VALUES (?, 'mention', '{"opportunity_id": 1}')
            """,
            (other["id"],),
        )
        connection.commit()
        other_notification_id = connection.execute(
            "SELECT id FROM notifications WHERE user_id = ?",
            (other["id"],),
        ).fetchone()["id"]

    login(client, "viewer@example.com")
    notifications = client.get("/api/notifications").json()["notifications"]
    assert len(notifications) == 1

    marked = client.patch(f"/api/notifications/{notifications[0]['id']}/read")
    assert marked.status_code == 200
    assert marked.json()["read"] is True
    assert client.get("/api/notifications").json()["notifications"] == []

    blocked = client.patch(f"/api/notifications/{other_notification_id}/read")
    assert blocked.status_code == 404
    assert owner["id"] == opportunity["owner_id"]


def test_follow_up_permissions_and_stalled_calculation(client: TestClient) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    client.post("/api/auth/logout")

    viewer = signup(client, "viewer@example.com", "Viewer")
    client.post("/api/auth/logout")
    share_opportunity(opportunity["id"], viewer["id"], owner["id"], "viewer")

    login(client, "viewer@example.com")
    blocked_follow_up = client.patch(
        f"/api/timeline/{entry['id']}",
        json={"follow_up_date": "2026-09-20"},
    )
    assert blocked_follow_up.status_code == 403
    client.post("/api/auth/logout")

    login(client, "owner@example.com")
    updated_follow_up = client.patch(
        f"/api/timeline/{entry['id']}",
        json={"follow_up_date": "2026-09-20"},
    )
    assert updated_follow_up.status_code == 200
    assert updated_follow_up.json()["follow_up_date"] == "2026-09-20"

    old_timestamp = (
        datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
    ).isoformat(timespec="seconds")
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

    stalled = client.get("/api/opportunities").json()["opportunities"][0]
    assert stalled["stalled"] is True

    note = client.post(
        f"/api/timeline/{entry['id']}/notes",
        json={"body": "Fresh follow up"},
    )
    assert note.status_code == 201

    refreshed = client.get("/api/opportunities").json()["opportunities"][0]
    assert refreshed["stalled"] is False
