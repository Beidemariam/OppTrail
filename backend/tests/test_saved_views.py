"""Saved views: a named filter + sort + group set (milestone 2.2).

Not opportunity-scoped, so `test_authorization_matrix.py` covers the actor
matrix (creator-only write, 404 for everyone else, per `CLAUDE.md`'s
absence-is-404 rule); this file covers the behaviour the matrix does not:
sharing visibility, the one-default-per-user invariant, and that a deleted
view really disappears from the list a caller who is not its creator sees.
"""

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


def create_view(client: TestClient, **overrides: object) -> dict:
    payload = {
        "name": "My pipeline",
        "entity": "opportunities",
        "filters": {"stage": "Negotiation"},
        "sort": {"field": "value", "direction": "desc"},
        "is_shared": False,
        "is_default": False,
    }
    payload.update(overrides)
    response = client.post("/api/v2/saved-views", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_and_read_back_a_saved_view(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    created = create_view(client)

    assert created["name"] == "My pipeline"
    assert created["entity"] == "opportunities"
    assert created["filters"] == {"stage": "Negotiation"}
    assert created["sort"] == {"field": "value", "direction": "desc"}
    assert created["is_shared"] is False
    assert created["is_default"] is False
    assert created["creator_name"] == "Owner"


def test_rejects_an_empty_name(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    response = client.post(
        "/api/v2/saved-views",
        json={"name": "", "entity": "opportunities"},
    )
    assert response.status_code == 422


def test_rejects_oversized_filter_parameters(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    response = client.post(
        "/api/v2/saved-views",
        json={
            "name": "Huge",
            "entity": "opportunities",
            "filters": {"q": "x" * 3000},
        },
    )
    assert response.status_code == 422


def test_list_includes_only_the_callers_own_and_shared_views(client: TestClient) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    login(client, "owner@example.com")
    private_view = create_view(client, name="Private", is_shared=False)
    shared_view = create_view(client, name="Shared", is_shared=True)

    other = signup(client, "other@example.com", "Other")
    login(client, "other@example.com")

    response = client.get("/api/v2/saved-views")
    assert response.status_code == 200
    names = {item["name"] for item in response.json()["items"]}
    assert names == {"Shared"}
    assert shared_view["id"] in {item["id"] for item in response.json()["items"]}
    assert private_view["id"] not in {item["id"] for item in response.json()["items"]}

    login(client, "owner@example.com")
    response = client.get("/api/v2/saved-views")
    names = {item["name"] for item in response.json()["items"]}
    assert names == {"Private", "Shared"}

    assert owner["id"] != other["id"]


def test_list_can_be_filtered_by_entity(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    create_view(client, name="Board view", entity="opportunities")
    create_view(client, name="Timeline order", entity="timeline", filters={"order": "desc"})

    response = client.get("/api/v2/saved-views?entity=timeline")
    items = response.json()["items"]
    assert [item["name"] for item in items] == ["Timeline order"]


def test_only_the_creator_can_update_or_delete_a_view(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    login(client, "owner@example.com")
    view = create_view(client, is_shared=True)

    signup(client, "other@example.com", "Other")
    login(client, "other@example.com")

    update = client.patch(f"/api/v2/saved-views/{view['id']}", json={"name": "Hijacked"})
    assert update.status_code == 404

    delete = client.delete(f"/api/v2/saved-views/{view['id']}")
    assert delete.status_code == 404

    login(client, "owner@example.com")
    update = client.patch(f"/api/v2/saved-views/{view['id']}", json={"name": "Renamed"})
    assert update.status_code == 200
    assert update.json()["name"] == "Renamed"


def test_delete_removes_the_view_from_the_list(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    view = create_view(client)

    delete = client.delete(f"/api/v2/saved-views/{view['id']}")
    assert delete.status_code == 204

    response = client.get("/api/v2/saved-views")
    assert response.json()["items"] == []

    # Deleting again finds nothing left to delete: same 404 a stranger gets,
    # not a special "already gone" case.
    assert client.delete(f"/api/v2/saved-views/{view['id']}").status_code == 404


def test_only_one_default_per_user_per_entity(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    first = create_view(client, name="First", is_default=True)
    second = create_view(client, name="Second", is_default=True)

    items = {item["id"]: item for item in client.get("/api/v2/saved-views").json()["items"]}
    assert items[first["id"]]["is_default"] is False
    assert items[second["id"]]["is_default"] is True

    # A default of a different entity does not touch the opportunities one.
    timeline_default = create_view(
        client, name="Timeline default", entity="timeline", is_default=True
    )
    items = {item["id"]: item for item in client.get("/api/v2/saved-views").json()["items"]}
    assert items[second["id"]]["is_default"] is True
    assert items[timeline_default["id"]]["is_default"] is True


def test_the_list_can_be_paged_with_a_cursor(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    for index in range(5):
        create_view(client, name=f"View {index}")

    items: list[dict] = []
    cursor: str | None = None
    pages = 0
    while True:
        query = "/api/v2/saved-views?limit=2" + (f"&cursor={cursor}" if cursor else "")
        body = client.get(query).json()
        items.extend(body["items"])
        cursor = body["next_cursor"]
        pages += 1
        if cursor is None:
            break
        assert pages < 10, "cursor walk did not terminate"

    assert pages == 3
    assert {item["name"] for item in items} == {f"View {index}" for index in range(5)}


def test_setting_default_via_update_also_clears_the_previous_one(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    first = create_view(client, name="First", is_default=True)
    second = create_view(client, name="Second", is_default=False)

    response = client.patch(f"/api/v2/saved-views/{second['id']}", json={"is_default": True})
    assert response.status_code == 200

    items = {item["id"]: item for item in client.get("/api/v2/saved-views").json()["items"]}
    assert items[first["id"]]["is_default"] is False
    assert items[second["id"]]["is_default"] is True
