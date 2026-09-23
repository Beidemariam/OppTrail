"""The calendar's follow-up layer (milestone 3.0b, **D-088**).

`GET /api/v2/timeline/follow-ups` is the third cross-opportunity read in the
app, after search and the bulk export routes -- same shape: the permission
filter is inside the query (`ACCESSIBLE_OPPORTUNITY_IDS_SQL`), so a page is
rows the caller may already read rather than rows filtered afterward.
"""

from fastapi.testclient import TestClient


def signup(client: TestClient, email: str = "owner@example.com", name: str = "Owner") -> dict:
    response = client.post(
        "/api/v2/auth/signup",
        json={"email": email, "password": "password123", "name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()["user"]


def login(client: TestClient, email: str) -> None:
    assert (
        client.post(
            "/api/v2/auth/login", json={"email": email, "password": "password123"}
        ).status_code
        == 200
    )


def create_opportunity(client: TestClient, name: str = "Northwind rollout") -> dict:
    response = client.post(
        "/api/v2/opportunities",
        json={
            "name": name,
            "account_name": "Northwind",
            "value": "25000",
            "currency": "USD",
            "stage": "Prospecting",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_entry(
    client: TestClient,
    opportunity_id: int,
    title: str = "Demo",
    entry_type: str = "demo",
    event_timestamp: str = "2026-09-01T10:00:00",
    follow_up_date: str | None = None,
) -> dict:
    payload = {
        "type": entry_type,
        "title": title,
        "body": "",
        "event_timestamp": event_timestamp,
    }
    if follow_up_date is not None:
        payload["follow_up_date"] = follow_up_date
    response = client.post(
        f"/api/v2/opportunities/{opportunity_id}/timeline",
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


def share(client: TestClient, opportunity_id: int, email: str, role: str) -> None:
    response = client.post(
        f"/api/v2/opportunities/{opportunity_id}/shares",
        json={"email": email, "role": role},
    )
    assert response.status_code == 201, response.text


def follow_ups(client: TestClient, **params: object) -> dict:
    suffix = "&".join(f"{key}={value}" for key, value in params.items())
    url = "/api/v2/timeline/follow-ups" + (f"?{suffix}" if suffix else "")
    response = client.get(url)
    assert response.status_code == 200, response.text
    return response.json()


def test_returns_only_entries_with_a_follow_up_date(client: TestClient) -> None:
    signup(client)
    opportunity = create_opportunity(client)
    dated = create_entry(client, opportunity["id"], follow_up_date="2026-09-20")
    create_entry(client, opportunity["id"], title="No follow-up")

    items = follow_ups(client)["items"]
    assert [item["id"] for item in items] == [dated["id"]]
    assert items[0]["follow_up_date"] == "2026-09-20"
    assert items[0]["opportunity_id"] == opportunity["id"]
    assert items[0]["opportunity_name"] == "Northwind rollout"


def test_scoped_to_what_the_caller_can_read(client: TestClient) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    viewer = signup(client, "viewer@example.com", "Viewer")
    stranger = signup(client, "stranger@example.com", "Stranger")
    assert owner["id"] != viewer["id"] != stranger["id"]

    login(client, "owner@example.com")
    shared = create_opportunity(client, "Shared deal")
    private = create_opportunity(client, "Private deal")
    shared_followup = create_entry(client, shared["id"], follow_up_date="2026-09-20")
    create_entry(client, private["id"], follow_up_date="2026-09-21")
    share(client, shared["id"], "viewer@example.com", "viewer")

    login(client, "viewer@example.com")
    assert [item["id"] for item in follow_ups(client)["items"]] == [shared_followup["id"]]

    login(client, "stranger@example.com")
    assert follow_ups(client)["items"] == []

    login(client, "owner@example.com")
    assert (
        client.delete(f"/api/v2/opportunities/{shared['id']}/shares/{viewer['id']}").status_code
        == 204
    )
    login(client, "viewer@example.com")
    assert follow_ups(client)["items"] == []


def test_filters_by_date_range(client: TestClient) -> None:
    signup(client)
    opportunity = create_opportunity(client)
    early = create_entry(client, opportunity["id"], title="Early", follow_up_date="2026-08-15")
    inside = create_entry(client, opportunity["id"], title="Inside", follow_up_date="2026-09-05")
    late = create_entry(client, opportunity["id"], title="Late", follow_up_date="2026-10-01")

    windowed = follow_ups(client, **{"from": "2026-09-01", "to": "2026-09-30"})
    assert [item["id"] for item in windowed["items"]] == [inside["id"]]

    assert {item["id"] for item in follow_ups(client, **{"to": "2026-08-31"})["items"]} == {
        early["id"]
    }
    assert {item["id"] for item in follow_ups(client, **{"from": "2026-10-01"})["items"]} == {
        late["id"]
    }


def test_orders_by_follow_up_date_then_id_and_pages_exactly_once(client: TestClient) -> None:
    signup(client)
    opportunity = create_opportunity(client)
    same_day = [
        create_entry(client, opportunity["id"], title=f"Entry {index}", follow_up_date="2026-09-10")
        for index in range(3)
    ]

    first_page = follow_ups(client, limit=2)
    assert [item["id"] for item in first_page["items"]] == [entry["id"] for entry in same_day[:2]]
    assert first_page["next_cursor"] is not None

    second_page = follow_ups(client, limit=2, cursor=first_page["next_cursor"])
    assert [item["id"] for item in second_page["items"]] == [same_day[2]["id"]]
    assert second_page["next_cursor"] is None


def test_soft_deleting_the_entry_removes_it(client: TestClient) -> None:
    signup(client)
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"], follow_up_date="2026-09-20")

    assert client.delete(f"/api/v2/timeline/{entry['id']}").status_code == 204

    assert follow_ups(client)["items"] == []


def test_soft_deleting_the_opportunity_removes_its_follow_ups(client: TestClient) -> None:
    signup(client)
    opportunity = create_opportunity(client)
    create_entry(client, opportunity["id"], follow_up_date="2026-09-20")

    assert client.delete(f"/api/v2/opportunities/{opportunity['id']}").status_code == 204

    assert follow_ups(client)["items"] == []
