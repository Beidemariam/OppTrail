from fastapi.testclient import TestClient

from app.database import db_connection


def signup(client: TestClient, email: str, name: str) -> None:
    response = client.post(
        "/api/v2/auth/signup",
        json={"email": email, "password": "password123", "name": name},
    )
    assert response.status_code == 201


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
            "currency": "usd",
            "stage": "Prospecting",
            "expected_close_date": "2026-10-15",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_owner_can_create_list_get_update_and_delete_opportunity(
    client: TestClient,
) -> None:
    signup(client, "owner@example.com", "Owner")

    opportunity = create_opportunity(client)
    assert opportunity["name"] == "Expansion"
    assert opportunity["currency"] == "USD"
    assert opportunity["stage"] == "Prospecting"

    listed = client.get("/api/v2/opportunities")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [opportunity["id"]]
    assert client.get("/api/v2/stages").json()["items"][0] == "Prospecting"

    fetched = client.get(f"/api/v2/opportunities/{opportunity['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["account_name"] == "Acme"

    updated = client.patch(
        f"/api/v2/opportunities/{opportunity['id']}",
        json={"stage": "Qualification", "value": "30000"},
    )
    assert updated.status_code == 200
    assert updated.json()["stage"] == "Qualification"
    assert updated.json()["value"] == "30000"

    timeline = client.get(f"/api/v2/opportunities/{opportunity['id']}/timeline")
    assert timeline.status_code == 200
    system_entries = timeline.json()["items"]
    assert [entry["title"] for entry in system_entries] == [
        "Opportunity created",
        "Stage changed to Qualification",
    ]
    assert all(entry["system_generated"] for entry in system_entries)
    assert client.delete(f"/api/v2/timeline/{system_entries[0]['id']}").status_code == 403

    deleted = client.delete(f"/api/v2/opportunities/{opportunity['id']}")
    assert deleted.status_code == 204
    with db_connection() as connection:
        active_timeline_rows = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM timeline_entries
            WHERE opportunity_id = ? AND deleted_at IS NULL
            """,
            (opportunity["id"],),
        ).fetchone()["count"]
    assert active_timeline_rows == 0

    missing = client.get(f"/api/v2/opportunities/{opportunity['id']}")
    assert missing.status_code == 404


def test_a_stage_only_update_logs_the_change_and_leaves_the_rest_alone(
    client: TestClient,
) -> None:
    """The request a board drag sends (milestone 2.7).

    The frontend moves a card by `PATCH`ing the stage on its own rather than
    resubmitting the whole form, so the fields nobody touched must come back
    unchanged and the move must still leave the system entry behind that makes
    it visible on the timeline.
    """
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)

    moved = client.patch(
        f"/api/v2/opportunities/{opportunity['id']}",
        json={"stage": "Proposal"},
    )
    assert moved.status_code == 200
    assert moved.json()["stage"] == "Proposal"
    assert moved.json()["value"] == opportunity["value"]
    assert moved.json()["name"] == opportunity["name"]
    assert moved.json()["expected_close_date"] == opportunity["expected_close_date"]

    timeline = client.get(f"/api/v2/opportunities/{opportunity['id']}/timeline")
    stage_changes = [entry for entry in timeline.json()["items"] if entry["type"] == "stage_change"]
    assert [entry["title"] for entry in stage_changes] == ["Stage changed to Proposal"]
    assert stage_changes[0]["body"] == "Stage changed from Prospecting to Proposal."
    assert stage_changes[0]["system_generated"]


def test_non_owner_cannot_view_or_mutate_opportunity(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    client.post("/api/v2/auth/logout")

    signup(client, "other@example.com", "Other")

    fetched = client.get(f"/api/v2/opportunities/{opportunity['id']}")
    assert fetched.status_code == 404

    updated = client.patch(
        f"/api/v2/opportunities/{opportunity['id']}",
        json={"stage": "Qualification"},
    )
    assert updated.status_code == 404

    deleted = client.delete(f"/api/v2/opportunities/{opportunity['id']}")
    assert deleted.status_code == 404

    listed = client.get("/api/v2/opportunities")
    assert listed.status_code == 200
    assert listed.json()["items"] == []


def test_shared_editor_can_view_but_not_mutate_opportunity(client: TestClient) -> None:
    """Editors/viewers have access (unlike `test_non_owner_...` above) but are
    not the owner, so mutation must be forbidden, not treated as not-found.

    Regression test for the permission-check consolidation onto
    `permissions.require_opportunity_owner` (D-004/D-007): before the
    consolidation, `PATCH`/`DELETE` used an inline owner-only query that
    returned 404 for *any* non-owner, including a shared editor who legitimately
    has read access. That collapsed "forbidden" and "not found" into one status
    code for a user who could see the opportunity via `GET`.
    """
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    client.post("/api/v2/auth/logout")

    signup(client, "editor@example.com", "Editor")
    client.post("/api/v2/auth/logout")

    login(client, "owner@example.com")
    added = client.post(
        f"/api/v2/opportunities/{opportunity['id']}/shares",
        json={"email": "editor@example.com", "role": "editor"},
    )
    assert added.status_code == 201
    client.post("/api/v2/auth/logout")

    login(client, "editor@example.com")

    fetched = client.get(f"/api/v2/opportunities/{opportunity['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["current_user_role"] == "editor"

    updated = client.patch(
        f"/api/v2/opportunities/{opportunity['id']}",
        json={"stage": "Qualification"},
    )
    assert updated.status_code == 403

    deleted = client.delete(f"/api/v2/opportunities/{opportunity['id']}")
    assert deleted.status_code == 403
