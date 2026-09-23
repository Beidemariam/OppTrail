"""The bulk opportunity endpoint (milestone 2.4c).

`docs/UX.md`: "Bulk operations are one request, transactional, and report
per-item failures rather than failing wholesale." These tests hold that
property — one id's failure does not take down the rest of the batch — plus
the two actions this milestone ships (`delete`, `set_stage`), both reusing the
single-item, owner-only rule `update_opportunity`/`delete_opportunity` already
enforce (D-070).

Milestone 3.0a added the two the action bar was missing -- `assign_owner`
(D-105) and `add_to_view` (D-106) -- and each brought a rule of its own:
ownership transfer is owner-only and leaves the previous owner behind as an
editor, while pinning to a view asks only for read access per id because it
writes to the caller's own saved view rather than to the opportunity. The
fifth action, export, is not here at all: it answers with a file (D-107,
`tests/test_export.py`).
"""

import pytest
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


# --- Assign owner (milestone 3.0a, D-105) -----------------------------------


def create_saved_view(client: TestClient, name: str = "My deals", **overrides) -> dict:
    payload = {"name": name, "entity": "opportunities", "filters": {}, "sort": {}}
    payload.update(overrides)
    response = client.post("/api/v2/saved-views", json=payload)
    assert response.status_code == 201
    return response.json()


def test_assign_owner_hands_the_record_over_and_keeps_the_previous_owner(
    client: TestClient,
) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    client.post("/api/v2/auth/logout")
    successor = signup(client, "successor@example.com", "Successor")
    client.post("/api/v2/auth/logout")

    login(client, "owner@example.com")
    opportunity = create_opportunity(client, "Expansion")

    response = client.post(
        "/api/v2/opportunities/bulk",
        json={
            "ids": [opportunity["id"]],
            "action": "assign_owner",
            "new_owner_email": "successor@example.com",
        },
    )
    assert response.status_code == 200
    assert results_by_id(response.json())[opportunity["id"]]["status"] == "ok"

    # The previous owner keeps access, as an editor rather than as nothing:
    # a handover is not a lockout (D-105).
    after = client.get(f"/api/v2/opportunities/{opportunity['id']}")
    assert after.status_code == 200
    assert after.json()["owner_id"] == successor["id"]
    assert after.json()["owner_name"] == "Successor"
    assert after.json()["current_user_role"] == "editor"

    # Sharing is owner-only, so the previous owner can no longer read it --
    # which is the whole point of the transfer.
    assert client.get(f"/api/v2/opportunities/{opportunity['id']}/shares").status_code == 403
    client.post("/api/v2/auth/logout")

    login(client, "successor@example.com")
    shares = client.get(f"/api/v2/opportunities/{opportunity['id']}/shares")
    assert shares.status_code == 200
    assert [(share["email"], share["role"]) for share in shares.json()["items"]] == [
        ("owner@example.com", "editor")
    ]

    # Recorded the way sharing is: a system entry everyone with access reads,
    # and an audit row for the owner's forensics.
    timeline = client.get(f"/api/v2/opportunities/{opportunity['id']}/timeline").json()
    assert "Owner changed to Successor" in [
        entry["title"] for entry in timeline["items"] if entry["system_generated"]
    ]

    audit = client.get(f"/api/v2/opportunities/{opportunity['id']}/audit-log").json()
    owner_rows = [row for row in audit["items"] if row["action"] == "owner_changed"]
    assert len(owner_rows) == 1
    assert owner_rows[0]["actor_id"] == owner["id"]
    assert owner_rows[0]["detail"] == {
        "from_user_id": owner["id"],
        "to_user_id": successor["id"],
        "to_email": "successor@example.com",
    }

    # Being handed a deal is an access change nobody asked for, so it is told.
    notifications = client.get("/api/v2/notifications?type=owner_changed").json()
    assert [item["payload"] for item in notifications["items"]] == [
        {"opportunity_id": opportunity["id"], "actor_id": owner["id"]}
    ]


def test_assign_owner_writes_no_version_because_ownership_is_not_an_edit(
    client: TestClient,
) -> None:
    signup(client, "owner@example.com", "Owner")
    client.post("/api/v2/auth/logout")
    signup(client, "successor@example.com", "Successor")
    client.post("/api/v2/auth/logout")

    login(client, "owner@example.com")
    opportunity = create_opportunity(client)
    before = client.get(f"/api/v2/opportunities/{opportunity['id']}/versions").json()

    client.post(
        "/api/v2/opportunities/bulk",
        json={
            "ids": [opportunity["id"]],
            "action": "assign_owner",
            "new_owner_email": "successor@example.com",
        },
    )
    client.post("/api/v2/auth/logout")
    login(client, "successor@example.com")

    after = client.get(f"/api/v2/opportunities/{opportunity['id']}/versions").json()
    assert [row["version_number"] for row in after["items"]] == [
        row["version_number"] for row in before["items"]
    ]


def test_assign_owner_removes_the_new_owners_share_row(client: TestClient) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    client.post("/api/v2/auth/logout")
    editor = signup(client, "editor@example.com", "Editor")
    client.post("/api/v2/auth/logout")

    login(client, "owner@example.com")
    opportunity = create_opportunity(client)
    share_opportunity(opportunity["id"], editor["id"], owner["id"], "editor")

    client.post(
        "/api/v2/opportunities/bulk",
        json={
            "ids": [opportunity["id"]],
            "action": "assign_owner",
            "new_owner_email": "editor@example.com",
        },
    )
    client.post("/api/v2/auth/logout")

    # The new owner holds the record, so they are not also a guest on it.
    login(client, "editor@example.com")
    shares = client.get(f"/api/v2/opportunities/{opportunity['id']}/shares").json()
    assert [share["email"] for share in shares["items"]] == ["owner@example.com"]


def test_assign_owner_reports_a_record_that_is_already_theirs(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)

    response = client.post(
        "/api/v2/opportunities/bulk",
        json={
            "ids": [opportunity["id"]],
            "action": "assign_owner",
            "new_owner_email": "owner@example.com",
        },
    )
    assert response.status_code == 200
    result = results_by_id(response.json())[opportunity["id"]]
    assert result["status"] == "error"
    assert result["error"] == "Opportunity is already owned by that user"


def test_assign_owner_to_an_unknown_email_fails_the_whole_request(
    client: TestClient,
) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)

    response = client.post(
        "/api/v2/opportunities/bulk",
        json={
            "ids": [opportunity["id"]],
            "action": "assign_owner",
            "new_owner_email": "nobody@example.com",
        },
    )
    # Wrong about the request rather than about one id, so nothing is applied.
    assert response.status_code == 404
    assert client.get(f"/api/v2/opportunities/{opportunity['id']}").json()["current_user_role"] == (
        "owner"
    )


def test_an_editor_cannot_assign_an_owner(client: TestClient) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    client.post("/api/v2/auth/logout")

    editor = signup(client, "editor@example.com", "Editor")
    share_opportunity(opportunity["id"], editor["id"], owner["id"], "editor")

    response = client.post(
        "/api/v2/opportunities/bulk",
        json={
            "ids": [opportunity["id"]],
            "action": "assign_owner",
            "new_owner_email": "editor@example.com",
        },
    )
    assert response.status_code == 200
    result = results_by_id(response.json())[opportunity["id"]]
    assert result["status"] == "error"
    assert (
        client.get(f"/api/v2/opportunities/{opportunity['id']}").json()["owner_id"] == (owner["id"])
    )


# --- Add to view (milestone 3.0a, D-106) ------------------------------------


def test_add_to_view_pins_the_selection_into_the_callers_own_view(
    client: TestClient,
) -> None:
    signup(client, "owner@example.com", "Owner")
    first = create_opportunity(client, "First")
    second = create_opportunity(client, "Second")
    view = create_saved_view(client, filters={"stage": "Prospecting"})

    response = client.post(
        "/api/v2/opportunities/bulk",
        json={
            "ids": [first["id"], second["id"]],
            "action": "add_to_view",
            "view_id": view["id"],
        },
    )
    assert response.status_code == 200
    assert [item["status"] for item in response.json()["results"]] == ["ok", "ok"]

    views = client.get("/api/v2/saved-views?entity=opportunities").json()
    stored = next(item for item in views["items"] if item["id"] == view["id"])
    # An id filter like any other filter -- no membership table, and the
    # view's other filters are left alone (D-106).
    assert stored["filters"] == {
        "stage": "Prospecting",
        "ids": f"{first['id']},{second['id']}",
    }


def test_add_to_view_is_additive_and_ignores_what_is_already_pinned(
    client: TestClient,
) -> None:
    signup(client, "owner@example.com", "Owner")
    first = create_opportunity(client, "First")
    second = create_opportunity(client, "Second")
    view = create_saved_view(client)

    def pin(ids: list[int]) -> None:
        response = client.post(
            "/api/v2/opportunities/bulk",
            json={"ids": ids, "action": "add_to_view", "view_id": view["id"]},
        )
        assert response.status_code == 200

    pin([first["id"]])
    pin([first["id"], second["id"]])

    views = client.get("/api/v2/saved-views?entity=opportunities").json()
    stored = next(item for item in views["items"] if item["id"] == view["id"])
    assert stored["filters"]["ids"] == f"{first['id']},{second['id']}"


def test_a_viewer_can_pin_a_shared_opportunity_to_their_own_view(
    client: TestClient,
) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    client.post("/api/v2/auth/logout")

    viewer = signup(client, "viewer@example.com", "Viewer")
    share_opportunity(opportunity["id"], viewer["id"], owner["id"], "viewer")
    view = create_saved_view(client, name="Watching")

    # Pinning writes to the reader's own view, not to the opportunity, so
    # read access is the whole rule (D-106).
    response = client.post(
        "/api/v2/opportunities/bulk",
        json={"ids": [opportunity["id"]], "action": "add_to_view", "view_id": view["id"]},
    )
    assert response.status_code == 200
    assert results_by_id(response.json())[opportunity["id"]]["status"] == "ok"

    views = client.get("/api/v2/saved-views?entity=opportunities").json()
    stored = next(item for item in views["items"] if item["id"] == view["id"])
    assert stored["filters"]["ids"] == str(opportunity["id"])


def test_add_to_view_reports_an_opportunity_the_caller_cannot_read(
    client: TestClient,
) -> None:
    signup(client, "owner@example.com", "Owner")
    hidden = create_opportunity(client, "Hidden")
    client.post("/api/v2/auth/logout")

    signup(client, "outsider@example.com", "Outsider")
    mine = create_opportunity(client, "Mine")
    view = create_saved_view(client)

    response = client.post(
        "/api/v2/opportunities/bulk",
        json={
            "ids": [hidden["id"], mine["id"]],
            "action": "add_to_view",
            "view_id": view["id"],
        },
    )
    assert response.status_code == 200
    results = results_by_id(response.json())
    assert results[hidden["id"]]["status"] == "error"
    assert results[hidden["id"]]["error"] == "Opportunity not found"
    assert results[mine["id"]]["status"] == "ok"

    views = client.get("/api/v2/saved-views?entity=opportunities").json()
    stored = next(item for item in views["items"] if item["id"] == view["id"])
    assert stored["filters"]["ids"] == str(mine["id"])


def test_add_to_view_refuses_a_view_that_is_not_the_callers(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    theirs = create_saved_view(client, name="Theirs", is_shared=True)
    client.post("/api/v2/auth/logout")

    signup(client, "outsider@example.com", "Outsider")
    opportunity = create_opportunity(client)

    # Readable, because it is shared -- and still not writable. A view that is
    # not the caller's answers 404 rather than 403, like everything else here.
    response = client.post(
        "/api/v2/opportunities/bulk",
        json={"ids": [opportunity["id"]], "action": "add_to_view", "view_id": theirs["id"]},
    )
    assert response.status_code == 404


def test_add_to_view_refuses_a_view_over_a_different_entity(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    timeline_view = create_saved_view(client, name="Recent calls", entity="timeline")

    response = client.post(
        "/api/v2/opportunities/bulk",
        json={
            "ids": [opportunity["id"]],
            "action": "add_to_view",
            "view_id": timeline_view["id"],
        },
    )
    assert response.status_code == 400


def test_add_to_view_refuses_more_than_a_view_can_hold(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    # A view already close to the size cap a saved view may carry: one more
    # filter value pushes it over, and the reader is told rather than having
    # the tail silently dropped.
    view = create_saved_view(client, filters={"q": "x" * 1980})

    response = client.post(
        "/api/v2/opportunities/bulk",
        json={"ids": [opportunity["id"]], "action": "add_to_view", "view_id": view["id"]},
    )
    assert response.status_code == 400
    assert "too large" in response.json()["error"]["message"]


# --- Which field belongs to which action ------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "assign_owner"},
        {"action": "add_to_view"},
        {"action": "assign_owner", "view_id": 1},
        {"action": "add_to_view", "new_owner_email": "someone@example.com"},
        {"action": "set_stage", "stage": "Qualification", "view_id": 1},
        {"action": "delete", "new_owner_email": "someone@example.com"},
    ],
)
def test_an_action_refuses_a_field_that_is_not_its_own(client: TestClient, payload: dict) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)

    response = client.post(
        "/api/v2/opportunities/bulk",
        json={"ids": [opportunity["id"]], **payload},
    )
    assert response.status_code == 422


def test_assign_owner_with_an_empty_email_is_a_lookup_that_fails(
    client: TestClient,
) -> None:
    """The validator ties `new_owner_email` to this action but cannot know
    which addresses exist, so an empty one is answered by the lookup rather
    than skipping it -- which would have reported `ok` for a transfer that
    never happened."""
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)

    response = client.post(
        "/api/v2/opportunities/bulk",
        json={
            "ids": [opportunity["id"]],
            "action": "assign_owner",
            "new_owner_email": "",
        },
    )
    assert response.status_code == 404
    assert (
        client.get(f"/api/v2/opportunities/{opportunity['id']}").json()["owner_id"]
        == (client.get("/api/v2/auth/me").json()["user"]["id"])
    )
