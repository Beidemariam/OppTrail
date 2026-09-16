from fastapi.testclient import TestClient


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


def test_owner_can_manage_shares_and_audit_history(client: TestClient) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    client.post("/api/auth/logout")

    editor = signup(client, "editor@example.com", "Editor")
    client.post("/api/auth/logout")
    login(client, "owner@example.com")

    added = client.post(
        f"/api/opportunities/{opportunity['id']}/shares",
        json={"email": "editor@example.com", "role": "viewer"},
    )
    assert added.status_code == 201
    assert added.json()["user_id"] == editor["id"]
    assert added.json()["role"] == "viewer"

    listed = client.get(f"/api/opportunities/{opportunity['id']}/shares")
    assert listed.status_code == 200
    assert [share["email"] for share in listed.json()["shares"]] == ["editor@example.com"]

    updated = client.patch(
        f"/api/opportunities/{opportunity['id']}/shares/{editor['id']}",
        json={"role": "editor"},
    )
    assert updated.status_code == 200
    assert updated.json()["role"] == "editor"

    timeline = client.get(f"/api/opportunities/{opportunity['id']}/timeline")
    assert timeline.status_code == 200
    assert [
        entry["title"] for entry in timeline.json()["entries"] if entry["system_generated"]
    ] == [
        "Opportunity created",
        "Shared with Editor",
        "Role changed for Editor",
    ]

    audit = client.get(f"/api/opportunities/{opportunity['id']}/audit-log")
    assert audit.status_code == 200
    assert [row["action"] for row in audit.json()] == [
        "share_added",
        "share_role_changed",
    ]
    assert all(row["actor_id"] == owner["id"] for row in audit.json())

    deleted = client.delete(f"/api/opportunities/{opportunity['id']}/shares/{editor['id']}")
    assert deleted.status_code == 204

    shares_after_delete = client.get(f"/api/opportunities/{opportunity['id']}/shares")
    assert shares_after_delete.status_code == 200
    assert shares_after_delete.json()["shares"] == []
    client.post("/api/auth/logout")

    login(client, "editor@example.com")
    dashboard_after_delete = client.get("/api/opportunities")
    assert dashboard_after_delete.status_code == 200
    assert dashboard_after_delete.json()["opportunities"] == []
    client.post("/api/auth/logout")

    login(client, "owner@example.com")
    audit_after_delete = client.get(f"/api/opportunities/{opportunity['id']}/audit-log")
    assert [row["action"] for row in audit_after_delete.json()] == [
        "share_added",
        "share_role_changed",
        "share_removed",
    ]


def test_shared_user_dashboard_and_permissions_follow_role(
    client: TestClient,
) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    client.post("/api/auth/logout")
    editor = signup(client, "editor@example.com", "Editor")
    client.post("/api/auth/logout")

    login(client, "owner@example.com")
    response = client.post(
        f"/api/opportunities/{opportunity['id']}/shares",
        json={"email": "editor@example.com", "role": "viewer"},
    )
    assert response.status_code == 201
    client.post("/api/auth/logout")

    login(client, "editor@example.com")
    dashboard = client.get("/api/opportunities")
    assert [item["id"] for item in dashboard.json()["opportunities"]] == [opportunity["id"]]
    blocked = client.post(
        f"/api/opportunities/{opportunity['id']}/timeline",
        json={
            "type": "call",
            "title": "Viewer call",
            "body": "Blocked",
            "event_timestamp": "2026-09-04T10:00",
        },
    )
    assert blocked.status_code == 403
    client.post("/api/auth/logout")

    login(client, "owner@example.com")
    promoted = client.patch(
        f"/api/opportunities/{opportunity['id']}/shares/{editor['id']}",
        json={"role": "editor"},
    )
    assert promoted.status_code == 200
    client.post("/api/auth/logout")

    login(client, "editor@example.com")
    created = client.post(
        f"/api/opportunities/{opportunity['id']}/timeline",
        json={
            "type": "call",
            "title": "Editor call",
            "body": "Allowed",
            "event_timestamp": "2026-09-04T10:00",
        },
    )
    assert created.status_code == 201

    share_attempt = client.post(
        f"/api/opportunities/{opportunity['id']}/shares",
        json={"email": "owner@example.com", "role": "viewer"},
    )
    assert share_attempt.status_code == 403

    audit_attempt = client.get(f"/api/opportunities/{opportunity['id']}/audit-log")
    assert audit_attempt.status_code == 403


def test_non_owner_cannot_manage_shares_or_audit_log(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    client.post("/api/auth/logout")
    signup(client, "other@example.com", "Other")

    listed = client.get(f"/api/opportunities/{opportunity['id']}/shares")
    assert listed.status_code == 404

    created = client.post(
        f"/api/opportunities/{opportunity['id']}/shares",
        json={"email": "other@example.com", "role": "viewer"},
    )
    assert created.status_code == 404

    audit = client.get(f"/api/opportunities/{opportunity['id']}/audit-log")
    assert audit.status_code == 404


def test_share_validation_errors(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)

    missing = client.post(
        f"/api/opportunities/{opportunity['id']}/shares",
        json={"email": "missing@example.com", "role": "viewer"},
    )
    assert missing.status_code == 404

    self_share = client.post(
        f"/api/opportunities/{opportunity['id']}/shares",
        json={"email": "owner@example.com", "role": "viewer"},
    )
    assert self_share.status_code == 400
