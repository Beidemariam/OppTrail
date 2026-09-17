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


def test_login_purges_expired_sessions(client: TestClient) -> None:
    signup(client)

    with db_connection() as connection:
        connection.execute("UPDATE sessions SET expires_at = '2000-01-01T00:00:00Z'")
        connection.commit()

    client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "password123"},
    )

    with db_connection() as connection:
        rows = connection.execute(
            "SELECT expires_at FROM sessions WHERE expires_at = '2000-01-01T00:00:00Z'"
        ).fetchall()
    assert rows == []


def test_password_change_requires_the_current_password(client: TestClient) -> None:
    signup(client)

    response = client.post(
        "/api/auth/password",
        json={"current_password": "wrong-password", "new_password": "new-password123"},
    )

    assert response.status_code == 401
    # The old password still works.
    client.post("/api/auth/logout")
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "owner@example.com", "password": "password123"},
        ).status_code
        == 200
    )


def test_password_change_requires_authentication(client: TestClient) -> None:
    response = client.post(
        "/api/auth/password",
        json={"current_password": "password123", "new_password": "new-password123"},
    )

    assert response.status_code == 401


def test_password_change_rejects_a_short_new_password(client: TestClient) -> None:
    signup(client)

    response = client.post(
        "/api/auth/password",
        json={"current_password": "password123", "new_password": "short"},
    )

    assert response.status_code == 422


def test_password_change_invalidates_every_other_session(client: TestClient) -> None:
    """The point of the endpoint: a session stolen before the change stops
    working after it, including on another device.
    """
    user = signup(client)
    other_device = client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "password123"},
    )
    assert other_device.status_code == 200
    stolen_session = client.cookies["opptrail_session"]

    changed = client.post(
        "/api/auth/password",
        json={"current_password": "password123", "new_password": "new-password123"},
    )

    assert changed.status_code == 200
    assert changed.json()["user"]["id"] == user["id"]
    # The caller is re-issued a working session; the old one is gone.
    assert client.cookies["opptrail_session"] != stolen_session
    assert client.get("/api/auth/me").status_code == 200
    with db_connection() as connection:
        sessions = connection.execute("SELECT id FROM sessions").fetchall()
    assert [row["id"] for row in sessions] == [client.cookies["opptrail_session"]]


def test_the_new_password_is_the_one_that_works(client: TestClient) -> None:
    signup(client)
    client.post(
        "/api/auth/password",
        json={"current_password": "password123", "new_password": "new-password123"},
    )
    client.post("/api/auth/logout")

    assert (
        client.post(
            "/api/auth/login",
            json={"email": "owner@example.com", "password": "password123"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "owner@example.com", "password": "new-password123"},
        ).status_code
        == 200
    )
