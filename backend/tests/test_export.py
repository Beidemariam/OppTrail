import csv
from io import StringIO

from fastapi.testclient import TestClient

from app.database import db_connection


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


def create_entry(
    client: TestClient,
    opportunity_id: int,
    title: str,
    event_timestamp: str,
) -> dict:
    response = client.post(
        f"/api/opportunities/{opportunity_id}/timeline",
        json={
            "type": "call",
            "title": title,
            "body": f"{title} details",
            "event_timestamp": event_timestamp,
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


def add_note_and_comment(client: TestClient, entry_id: int) -> tuple[dict, dict]:
    note_response = client.post(
        f"/api/timeline/{entry_id}/notes",
        json={"body": "Procurement follow-up needed"},
    )
    assert note_response.status_code == 201
    note = note_response.json()
    comment_response = client.post(
        f"/api/notes/{note['id']}/comments",
        json={"body": "Loop in legal before Friday"},
    )
    assert comment_response.status_code == 201
    return note, comment_response.json()


def test_export_json_csv_and_pdf_for_owner(client: TestClient, monkeypatch) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    later_entry = create_entry(
        client,
        opportunity["id"],
        "Later call",
        "2026-09-04T13:00:00",
    )
    earlier_entry = create_entry(
        client,
        opportunity["id"],
        "Earlier call",
        "2026-09-01T09:00:00",
    )
    note, comment = add_note_and_comment(client, later_entry["id"])
    hidden_entry = create_entry(
        client,
        opportunity["id"],
        "Hidden call",
        "2026-09-02T09:00:00",
    )
    assert client.delete(f"/api/timeline/{hidden_entry['id']}").status_code == 204

    json_response = client.get(f"/api/opportunities/{opportunity['id']}/export/json")
    assert json_response.status_code == 200
    assert "attachment" in json_response.headers["content-disposition"]
    data = json_response.json()
    titles = [entry["title"] for entry in data["entries"]]
    timestamps = [entry["event_timestamp"] for entry in data["entries"]]
    assert "Hidden call" not in titles
    assert timestamps == sorted(timestamps)
    exported_later = next(entry for entry in data["entries"] if entry["id"] == later_entry["id"])
    assert exported_later["notes"][0]["id"] == note["id"]
    assert exported_later["notes"][0]["comments"][0]["id"] == comment["id"]

    csv_response = client.get(f"/api/opportunities/{opportunity['id']}/export/csv")
    assert csv_response.status_code == 200
    assert csv_response.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(StringIO(csv_response.text)))
    assert {row["row_type"] for row in rows} >= {"entry", "note", "comment"}
    note_row = next(row for row in rows if row["row_type"] == "note")
    comment_row = next(row for row in rows if row["row_type"] == "comment")
    assert note_row["parent_entry_id"] == str(later_entry["id"])
    assert comment_row["parent_note_id"] == str(note["id"])

    monkeypatch.setattr("app.routes_export.export_data_to_pdf", lambda data: b"%PDF-1.7")
    pdf_response = client.get(f"/api/opportunities/{opportunity['id']}/export/pdf")
    assert pdf_response.status_code == 200
    assert pdf_response.headers["content-type"].startswith("application/pdf")
    assert pdf_response.content.startswith(b"%PDF")
    assert earlier_entry["title"] in titles


def test_shared_users_can_export_and_unshared_user_cannot(
    client: TestClient,
    monkeypatch,
) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    create_entry(client, opportunity["id"], "Shared call", "2026-09-04T10:00:00")
    client.post("/api/auth/logout")

    editor = signup(client, "editor@example.com", "Editor")
    client.post("/api/auth/logout")
    viewer = signup(client, "viewer@example.com", "Viewer")
    client.post("/api/auth/logout")
    other = signup(client, "other@example.com", "Other")
    client.post("/api/auth/logout")

    share_opportunity(opportunity["id"], editor["id"], owner["id"], "editor")
    share_opportunity(opportunity["id"], viewer["id"], owner["id"], "viewer")
    monkeypatch.setattr("app.routes_export.export_data_to_pdf", lambda data: b"%PDF-1.7")

    login(client, "editor@example.com")
    assert client.get(f"/api/opportunities/{opportunity['id']}/export/csv").status_code == 200
    client.post("/api/auth/logout")

    login(client, "viewer@example.com")
    assert client.get(f"/api/opportunities/{opportunity['id']}/export/json").status_code == 200
    client.post("/api/auth/logout")

    login(client, "other@example.com")
    assert other["email"] == "other@example.com"
    assert client.get(f"/api/opportunities/{opportunity['id']}/export/json").status_code == 404
    assert client.get(f"/api/opportunities/{opportunity['id']}/export/csv").status_code == 404
    assert client.get(f"/api/opportunities/{opportunity['id']}/export/pdf").status_code == 404
