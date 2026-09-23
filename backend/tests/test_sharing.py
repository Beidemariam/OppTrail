from fastapi.testclient import TestClient


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


def test_owner_can_manage_shares_and_audit_history(client: TestClient) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    client.post("/api/v2/auth/logout")

    editor = signup(client, "editor@example.com", "Editor")
    client.post("/api/v2/auth/logout")
    login(client, "owner@example.com")

    added = client.post(
        f"/api/v2/opportunities/{opportunity['id']}/shares",
        json={"email": "editor@example.com", "role": "viewer"},
    )
    assert added.status_code == 201
    assert added.json()["user_id"] == editor["id"]
    assert added.json()["role"] == "viewer"

    listed = client.get(f"/api/v2/opportunities/{opportunity['id']}/shares")
    assert listed.status_code == 200
    assert [share["email"] for share in listed.json()["items"]] == ["editor@example.com"]

    updated = client.patch(
        f"/api/v2/opportunities/{opportunity['id']}/shares/{editor['id']}",
        json={"role": "editor"},
    )
    assert updated.status_code == 200
    assert updated.json()["role"] == "editor"

    timeline = client.get(f"/api/v2/opportunities/{opportunity['id']}/timeline")
    assert timeline.status_code == 200
    assert [entry["title"] for entry in timeline.json()["items"] if entry["system_generated"]] == [
        "Opportunity created",
        "Shared with Editor",
        "Role changed for Editor",
    ]

    audit = client.get(f"/api/v2/opportunities/{opportunity['id']}/audit-log")
    assert audit.status_code == 200
    assert [row["action"] for row in audit.json()["items"]] == [
        "share_added",
        "share_role_changed",
    ]
    assert all(row["actor_id"] == owner["id"] for row in audit.json()["items"])

    deleted = client.delete(f"/api/v2/opportunities/{opportunity['id']}/shares/{editor['id']}")
    assert deleted.status_code == 204

    shares_after_delete = client.get(f"/api/v2/opportunities/{opportunity['id']}/shares")
    assert shares_after_delete.status_code == 200
    assert shares_after_delete.json()["items"] == []
    client.post("/api/v2/auth/logout")

    login(client, "editor@example.com")
    dashboard_after_delete = client.get("/api/v2/opportunities")
    assert dashboard_after_delete.status_code == 200
    assert dashboard_after_delete.json()["items"] == []
    client.post("/api/v2/auth/logout")

    login(client, "owner@example.com")
    audit_after_delete = client.get(f"/api/v2/opportunities/{opportunity['id']}/audit-log")
    assert [row["action"] for row in audit_after_delete.json()["items"]] == [
        "share_added",
        "share_role_changed",
        "share_removed",
    ]


def test_shared_user_dashboard_and_permissions_follow_role(
    client: TestClient,
) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    client.post("/api/v2/auth/logout")
    editor = signup(client, "editor@example.com", "Editor")
    client.post("/api/v2/auth/logout")

    login(client, "owner@example.com")
    response = client.post(
        f"/api/v2/opportunities/{opportunity['id']}/shares",
        json={"email": "editor@example.com", "role": "viewer"},
    )
    assert response.status_code == 201
    client.post("/api/v2/auth/logout")

    login(client, "editor@example.com")
    dashboard = client.get("/api/v2/opportunities")
    assert [item["id"] for item in dashboard.json()["items"]] == [opportunity["id"]]
    blocked = client.post(
        f"/api/v2/opportunities/{opportunity['id']}/timeline",
        json={
            "type": "call",
            "title": "Viewer call",
            "body": "Blocked",
            "event_timestamp": "2026-09-04T10:00",
        },
    )
    assert blocked.status_code == 403
    client.post("/api/v2/auth/logout")

    login(client, "owner@example.com")
    promoted = client.patch(
        f"/api/v2/opportunities/{opportunity['id']}/shares/{editor['id']}",
        json={"role": "editor"},
    )
    assert promoted.status_code == 200
    client.post("/api/v2/auth/logout")

    login(client, "editor@example.com")
    created = client.post(
        f"/api/v2/opportunities/{opportunity['id']}/timeline",
        json={
            "type": "call",
            "title": "Editor call",
            "body": "Allowed",
            "event_timestamp": "2026-09-04T10:00",
        },
    )
    assert created.status_code == 201

    share_attempt = client.post(
        f"/api/v2/opportunities/{opportunity['id']}/shares",
        json={"email": "owner@example.com", "role": "viewer"},
    )
    assert share_attempt.status_code == 403

    audit_attempt = client.get(f"/api/v2/opportunities/{opportunity['id']}/audit-log")
    assert audit_attempt.status_code == 403


def test_a_removed_share_can_be_granted_again(client: TestClient) -> None:
    """`soft_delete_share` stamps the row rather than removing it, and
    `UNIQUE (opportunity_id, user_id)` means a second grant is an update of
    that row. `share_utils.upsert_share_row` is the one place both paths --
    this one and milestone 3.0a's ownership transfer -- write it."""
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    client.post("/api/v2/auth/logout")

    colleague = signup(client, "colleague@example.com", "Colleague")
    client.post("/api/v2/auth/logout")
    login(client, "owner@example.com")

    client.post(
        f"/api/v2/opportunities/{opportunity['id']}/shares",
        json={"email": "colleague@example.com", "role": "viewer"},
    )
    assert (
        client.delete(
            f"/api/v2/opportunities/{opportunity['id']}/shares/{colleague['id']}"
        ).status_code
        == 204
    )

    regranted = client.post(
        f"/api/v2/opportunities/{opportunity['id']}/shares",
        json={"email": "colleague@example.com", "role": "editor"},
    )
    assert regranted.status_code == 201
    # The revived row records this grant, not the one that was removed.
    assert regranted.json()["role"] == "editor"
    assert regranted.json()["invited_by"] == owner["id"]
    client.post("/api/v2/auth/logout")

    login(client, "colleague@example.com")
    assert client.get(f"/api/v2/opportunities/{opportunity['id']}").status_code == 200


def test_non_owner_cannot_manage_shares_or_audit_log(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    client.post("/api/v2/auth/logout")
    signup(client, "other@example.com", "Other")

    listed = client.get(f"/api/v2/opportunities/{opportunity['id']}/shares")
    assert listed.status_code == 404

    created = client.post(
        f"/api/v2/opportunities/{opportunity['id']}/shares",
        json={"email": "other@example.com", "role": "viewer"},
    )
    assert created.status_code == 404

    audit = client.get(f"/api/v2/opportunities/{opportunity['id']}/audit-log")
    assert audit.status_code == 404


def test_share_validation_errors(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)

    missing = client.post(
        f"/api/v2/opportunities/{opportunity['id']}/shares",
        json={"email": "missing@example.com", "role": "viewer"},
    )
    assert missing.status_code == 404

    self_share = client.post(
        f"/api/v2/opportunities/{opportunity['id']}/shares",
        json={"email": "owner@example.com", "role": "viewer"},
    )
    assert self_share.status_code == 400
