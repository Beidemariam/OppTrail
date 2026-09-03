from fastapi.testclient import TestClient

from app.database import db_connection, initialize_database


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

    timeline = client.get(f"/api/opportunities/{opportunity['id']}/timeline")
    assert timeline.status_code == 200
    system_entries = timeline.json()["entries"]
    assert [entry["title"] for entry in system_entries] == [
        "Opportunity created",
        "Stage changed to Qualification",
    ]
    assert all(entry["system_generated"] for entry in system_entries)
    assert client.delete(f"/api/timeline/{system_entries[0]['id']}").status_code == 403

    deleted = client.delete(f"/api/opportunities/{opportunity['id']}")
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

    missing = client.get(f"/api/opportunities/{opportunity['id']}")
    assert missing.status_code == 404


def test_schema_init_backfills_created_system_entries(client: TestClient) -> None:
    with db_connection() as connection:
        user = connection.execute(
            """
            INSERT INTO users (email, password_hash, name)
            VALUES ('legacy@example.com', 'hash', 'Legacy Owner')
            """
        )
        opportunity = connection.execute(
            """
            INSERT INTO opportunities (
                name,
                account_name,
                value,
                currency,
                stage,
                owner_id
            )
            VALUES ('Legacy Deal', 'Legacy Account', '1', 'USD', 'Prospecting', ?)
            """,
            (user.lastrowid,),
        )
        opportunity_id = int(opportunity.lastrowid)
        connection.commit()

    initialize_database()
    initialize_database()

    with db_connection() as connection:
        rows = connection.execute(
            """
            SELECT title, system_generated
            FROM timeline_entries
            WHERE opportunity_id = ? AND deleted_at IS NULL
            """,
            (opportunity_id,),
        ).fetchall()

    assert [row["title"] for row in rows] == ["Opportunity created"]
    assert rows[0]["system_generated"] == 1


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
