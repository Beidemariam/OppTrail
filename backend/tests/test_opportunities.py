from fastapi.testclient import TestClient


def signup(client: TestClient, email: str, name: str) -> None:
    response = client.post(
        "/api/auth/signup",
        json={"email": email, "password": "password123", "name": name},
    )
    assert response.status_code == 201


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

    listed = client.get("/api/opportunities")
    assert listed.status_code == 200
    assert listed.json()["stages"][0] == "Prospecting"
    assert [item["id"] for item in listed.json()["opportunities"]] == [opportunity["id"]]

    fetched = client.get(f"/api/opportunities/{opportunity['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["account_name"] == "Acme"

    updated = client.patch(
        f"/api/opportunities/{opportunity['id']}",
        json={"stage": "Qualification", "value": "30000"},
    )
    assert updated.status_code == 200
    assert updated.json()["stage"] == "Qualification"
    assert updated.json()["value"] == "30000"

    deleted = client.delete(f"/api/opportunities/{opportunity['id']}")
    assert deleted.status_code == 204

    missing = client.get(f"/api/opportunities/{opportunity['id']}")
    assert missing.status_code == 404


def test_non_owner_cannot_view_or_mutate_opportunity(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    client.post("/api/auth/logout")

    signup(client, "other@example.com", "Other")

    fetched = client.get(f"/api/opportunities/{opportunity['id']}")
    assert fetched.status_code == 404

    updated = client.patch(
        f"/api/opportunities/{opportunity['id']}",
        json={"stage": "Qualification"},
    )
    assert updated.status_code == 404

    deleted = client.delete(f"/api/opportunities/{opportunity['id']}")
    assert deleted.status_code == 404

    listed = client.get("/api/opportunities")
    assert listed.status_code == 200
    assert listed.json()["opportunities"] == []
