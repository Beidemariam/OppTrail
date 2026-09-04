from fastapi.testclient import TestClient

from app.ai_service import normalize_ai_answer
from app.database import db_connection
from app.settings import settings


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


def create_entry(client: TestClient, opportunity_id: int) -> dict:
    response = client.post(
        f"/api/opportunities/{opportunity_id}/timeline",
        json={
            "type": "call",
            "title": "Discovery call",
            "body": "Customer raised budget and legal objections.",
            "event_timestamp": "2026-09-04T10:00",
        },
    )
    assert response.status_code == 201
    return response.json()


def count_rows() -> dict[str, int]:
    with db_connection() as connection:
        return {
            "opportunities": connection.execute(
                "SELECT COUNT(*) AS count FROM opportunities"
            ).fetchone()["count"],
            "entries": connection.execute(
                "SELECT COUNT(*) AS count FROM timeline_entries"
            ).fetchone()["count"],
            "notes": connection.execute(
                "SELECT COUNT(*) AS count FROM notes"
            ).fetchone()["count"],
            "comments": connection.execute(
                "SELECT COUNT(*) AS count FROM comments"
            ).fetchone()["count"],
            "audit": connection.execute(
                "SELECT COUNT(*) AS count FROM audit_log_entries"
            ).fetchone()["count"],
        }


def test_ai_answer_uses_timeline_context_and_does_not_write(
    client: TestClient,
    monkeypatch,
) -> None:
    settings.openai_api_key = "test-key"
    settings.openai_model = "test-model"
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    note = client.post(
        f"/api/timeline/{entry['id']}/notes",
        json={"body": "Follow up with procurement next week."},
    )
    assert note.status_code == 201

    captured = {}

    def fake_ask_openai(
        api_key: str,
        model: str,
        timeline_context: str,
        question: str,
    ) -> str:
        captured["api_key"] = api_key
        captured["model"] = model
        captured["timeline_context"] = timeline_context
        captured["question"] = question
        return f"Budget and legal objections are open [Entry #{entry['id']}, 2026-09-04]."

    monkeypatch.setattr("app.routes_ai.ask_openai", fake_ask_openai)
    before_counts = count_rows()

    response = client.post(
        f"/api/opportunities/{opportunity['id']}/ai/ask",
        json={"question": "Where do we stand?"},
    )

    assert response.status_code == 200
    assert response.json()["referenced_entry_ids"] == [entry["id"]]
    assert "Budget and legal objections" in response.json()["answer"]
    assert captured["api_key"] == "test-key"
    assert captured["model"] == "test-model"
    assert "Discovery call" in captured["timeline_context"]
    assert "Follow up with procurement" in captured["timeline_context"]
    assert captured["question"] == "Where do we stand?"
    assert count_rows() == before_counts


def test_viewer_can_ask_ai_but_cannot_write(client: TestClient, monkeypatch) -> None:
    settings.openai_api_key = "test-key"
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    client.post("/api/auth/logout")
    viewer = signup(client, "viewer@example.com", "Viewer")
    client.post("/api/auth/logout")

    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO opportunity_shares (opportunity_id, user_id, role, invited_by)
            VALUES (?, ?, 'viewer', ?)
            """,
            (opportunity["id"], viewer["id"], owner["id"]),
        )
        connection.commit()

    monkeypatch.setattr(
        "app.routes_ai.ask_openai",
        lambda **kwargs: "Known from the shared timeline.",
    )

    login(client, "viewer@example.com")
    ai_response = client.post(
        f"/api/opportunities/{opportunity['id']}/ai/ask",
        json={"question": "Summarize this opportunity"},
    )
    assert ai_response.status_code == 200

    write_response = client.post(
        f"/api/opportunities/{opportunity['id']}/timeline",
        json={
            "type": "call",
            "title": "Viewer write",
            "body": "Should fail",
            "event_timestamp": "2026-09-04T10:00",
        },
    )
    assert write_response.status_code == 403


def test_ai_blocks_users_without_access(client: TestClient, monkeypatch) -> None:
    settings.openai_api_key = "test-key"
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    client.post("/api/auth/logout")
    signup(client, "other@example.com", "Other")

    called = False

    def fake_ask_openai(**kwargs) -> str:
        nonlocal called
        called = True
        return "Should not run"

    monkeypatch.setattr("app.routes_ai.ask_openai", fake_ask_openai)
    response = client.post(
        f"/api/opportunities/{opportunity['id']}/ai/ask",
        json={"question": "Can I see this?"},
    )

    assert response.status_code == 404
    assert called is False


def test_ai_returns_helpful_errors(client: TestClient, monkeypatch) -> None:
    settings.openai_api_key = None
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)

    missing_key = client.post(
        f"/api/opportunities/{opportunity['id']}/ai/ask",
        json={"question": "Summarize this opportunity"},
    )
    assert missing_key.status_code == 503

    settings.openai_api_key = "test-key"

    def broken_ask_openai(**kwargs) -> str:
        raise RuntimeError("network down")

    monkeypatch.setattr("app.routes_ai.ask_openai", broken_ask_openai)
    failed = client.post(
        f"/api/opportunities/{opportunity['id']}/ai/ask",
        json={"question": "Summarize this opportunity"},
    )
    assert failed.status_code == 502


def test_ai_answer_normalization_removes_markdown_bold_markers() -> None:
    answer = "- **Account:** Acme\n- **Value:** USD 25000"

    assert normalize_ai_answer(answer) == "- Account: Acme\n- Value: USD 25000"
