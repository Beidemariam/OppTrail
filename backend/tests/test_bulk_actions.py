"""The bulk opportunity endpoint (milestone 2.4c).

`docs/UX.md`: "Bulk operations are one request, transactional, and report
per-item failures rather than failing wholesale." These tests hold that
property — one id's failure does not take down the rest of the batch — plus
the two actions this milestone ships (`delete`, `set_stage`), both reusing the
single-item, owner-only rule `update_opportunity`/`delete_opportunity` already
enforce (D-070).
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


def results_by_id(response_json: dict) -> dict[int, dict]:
    return {item["id"]: item for item in response_json["results"]}


def test_owner_bulk_deletes_every_selected_opportunity(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    first = create_opportunity(client, "First")
    second = create_opportunity(client, "Second")

    response = client.post(
        "/api/v2/opportunities/bulk",
        json={"ids": [first["id"], second["id"]], "action": "delete"},
    )
    assert response.status_code == 200
    results = results_by_id(response.json())
    assert results[first["id"]] == {"id": first["id"], "status": "ok", "error": None}
    assert results[second["id"]] == {"id": second["id"], "status": "ok", "error": None}

    assert client.get(f"/api/v2/opportunities/{first['id']}").status_code == 404
    assert client.get(f"/api/v2/opportunities/{second['id']}").status_code == 404

    audit = client.get(f"/api/v2/opportunities/{first['id']}/audit-log")
    # The row itself is gone, so its own audit log 404s the same way the
    # opportunity does; the delete route already proves the audit write
    # (test_timeline.py). This just proves the bulk path took the same branch,
    # via the same 404-not-403 rule.
    assert audit.status_code == 404


def test_owner_bulk_changes_stage_and_logs_one_system_entry_per_item(
    client: TestClient,
) -> None:
    signup(client, "owner@example.com", "Owner")
    first = create_opportunity(client, "First")
    second = create_opportunity(client, "Second")

    response = client.post(
        "/api/v2/opportunities/bulk",
        json={
            "ids": [first["id"], second["id"]],
            "action": "set_stage",
            "stage": "Qualification",
        },
    )
    assert response.status_code == 200
    results = results_by_id(response.json())
    assert results[first["id"]]["status"] == "ok"
    assert results[second["id"]]["status"] == "ok"

    for opportunity_id in (first["id"], second["id"]):
        opportunity = client.get(f"/api/v2/opportunities/{opportunity_id}").json()
        assert opportunity["stage"] == "Qualification"

        timeline = client.get(f"/api/v2/opportunities/{opportunity_id}/timeline").json()
        stage_change_titles = [
            entry["title"] for entry in timeline["items"] if entry["type"] == "stage_change"
        ]
        assert stage_change_titles == ["Stage changed to Qualification"]


def test_bulk_set_stage_to_the_current_stage_writes_no_system_entry(
    client: TestClient,
) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)  # starts in Prospecting

    response = client.post(
        "/api/v2/opportunities/bulk",
        json={"ids": [opportunity["id"]], "action": "set_stage", "stage": "Prospecting"},
    )
    assert response.status_code == 200
    assert results_by_id(response.json())[opportunity["id"]]["status"] == "ok"

    timeline = client.get(f"/api/v2/opportunities/{opportunity['id']}/timeline").json()
    stage_change_titles = [
        entry["title"] for entry in timeline["items"] if entry["type"] == "stage_change"
    ]
    assert stage_change_titles == []


def test_bulk_action_reports_one_items_failure_without_failing_the_rest(
    client: TestClient,
) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    keeps = create_opportunity(client, "Keeps")

    login(client, "owner@example.com")
    signup(client, "editor@example.com", "Editor")
    editor_owned = create_opportunity(client, "Editor's own")

    login(client, "owner@example.com")
    share_opportunity(editor_owned["id"], owner["id"], editor_owned["owner_id"], "viewer")

    missing_id = editor_owned["id"] + 100_000

    response = client.post(
        "/api/v2/opportunities/bulk",
        json={"ids": [keeps["id"], editor_owned["id"], missing_id], "action": "delete"},
    )
    assert response.status_code == 200
    results = results_by_id(response.json())

    assert results[keeps["id"]]["status"] == "ok"
    assert results[editor_owned["id"]] == {
        "id": editor_owned["id"],
        "status": "error",
        "error": "Only the owner can manage this opportunity",
    }
    assert results[missing_id] == {
        "id": missing_id,
        "status": "error",
        "error": "Opportunity not found",
    }

    # The one legitimate delete happened despite the other two failing.
    assert client.get(f"/api/v2/opportunities/{keeps['id']}").status_code == 404
    # The one owned by someone else is untouched.
    assert client.get(f"/api/v2/opportunities/{editor_owned['id']}").status_code == 200


def test_unrelated_user_gets_not_found_for_every_id(client: TestClient) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)

    signup(client, "outsider@example.com", "Outsider")
    response = client.post(
        "/api/v2/opportunities/bulk",
        json={"ids": [opportunity["id"]], "action": "delete"},
    )
    assert response.status_code == 200
    results = results_by_id(response.json())
    assert results[opportunity["id"]]["status"] == "error"
    assert results[opportunity["id"]]["error"] == "Opportunity not found"

    login(client, "owner@example.com")
    assert client.get(f"/api/v2/opportunities/{opportunity['id']}").status_code == 200
    assert owner["id"]  # the fixture is read, not unused


def test_viewer_cannot_bulk_delete_a_shared_opportunity(client: TestClient) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)

    login(client, "owner@example.com")
    signup(client, "viewer@example.com", "Viewer")
    viewer_id = client.get("/api/v2/auth/me").json()["user"]["id"]

    login(client, "owner@example.com")
    share_opportunity(opportunity["id"], viewer_id, owner["id"], "viewer")

    login(client, "viewer@example.com")
    response = client.post(
        "/api/v2/opportunities/bulk",
        json={"ids": [opportunity["id"]], "action": "delete"},
    )
    assert response.status_code == 200
    results = results_by_id(response.json())
    assert results[opportunity["id"]] == {
        "id": opportunity["id"],
        "status": "error",
        "error": "Only the owner can manage this opportunity",
    }

    login(client, "owner@example.com")
    assert client.get(f"/api/v2/opportunities/{opportunity['id']}").status_code == 200


def test_the_same_id_twice_in_one_batch_deletes_once_and_fails_the_second(
    client: TestClient,
) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)

    response = client.post(
        "/api/v2/opportunities/bulk",
        json={"ids": [opportunity["id"], opportunity["id"]], "action": "delete"},
    )
    assert response.status_code == 200
    outcomes = [item["status"] for item in response.json()["results"]]
    # Processed left to right within the one connection: the first occurrence
    # deletes the row, so the second no longer finds it — an uncommitted write
    # is still visible to the connection that made it.
    assert outcomes == ["ok", "error"]


def test_anonymous_is_rejected_before_any_item_is_touched(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    client.post("/api/v2/auth/logout")

    response = client.post(
        "/api/v2/opportunities/bulk",
        json={"ids": [opportunity["id"]], "action": "delete"},
    )
    assert response.status_code == 401

    login(client, "owner@example.com")
    assert client.get(f"/api/v2/opportunities/{opportunity['id']}").status_code == 200


def test_set_stage_action_requires_a_stage(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)

    response = client.post(
        "/api/v2/opportunities/bulk",
        json={"ids": [opportunity["id"]], "action": "set_stage"},
    )
    assert response.status_code == 422


def test_delete_action_rejects_a_stage_field(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)

    response = client.post(
        "/api/v2/opportunities/bulk",
        json={"ids": [opportunity["id"]], "action": "delete", "stage": "Qualification"},
    )
    assert response.status_code == 422


def test_empty_ids_list_is_rejected(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")

    response = client.post(
        "/api/v2/opportunities/bulk",
        json={"ids": [], "action": "delete"},
    )
    assert response.status_code == 422
