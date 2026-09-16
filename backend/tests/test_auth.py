from fastapi.testclient import TestClient

from app.database import db_connection


def signup(client: TestClient, email: str = "owner@example.com") -> dict:
    response = client.post(
        "/api/auth/signup",
        json={"email": email, "password": "password123", "name": "Owner"},
    )
    assert response.status_code == 201
    return response.json()["user"]


def test_signup_sets_session_and_me_returns_user(client: TestClient) -> None:
    user = signup(client)

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["user"]["id"] == user["id"]
    assert response.json()["user"]["email"] == "owner@example.com"


def test_duplicate_signup_is_rejected(client: TestClient) -> None:
    signup(client)

    response = client.post(
        "/api/auth/signup",
        json={"email": "OWNER@example.com", "password": "password123", "name": "Owner"},
    )

    assert response.status_code == 409


def test_login_and_logout_flow(client: TestClient) -> None:
    signup(client)
    client.post("/api/auth/logout")

    login = client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "password123"},
    )
    assert login.status_code == 200

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200

    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_invalid_login_is_rejected(client: TestClient) -> None:
    signup(client)
    client.post("/api/auth/logout")

    response = client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 401


def test_protected_endpoint_requires_session(client: TestClient) -> None:
    response = client.get("/api/opportunities")

    assert response.status_code == 401


def test_logout_without_a_session_cookie_is_a_no_op(client: TestClient) -> None:
    response = client.post("/api/auth/logout")

    assert response.status_code == 200


def test_expired_or_unknown_session_cookie_is_rejected(client: TestClient) -> None:
    signup(client)

    with db_connection() as connection:
        connection.execute("UPDATE sessions SET expires_at = '2000-01-01T00:00:00Z'")
        connection.commit()

    response = client.get("/api/auth/me")

    assert response.status_code == 401
