"""CSRF protection, response security headers, and cookie/session hardening.

Every test here drives a plain `TestClient`, not the `CsrfClient` the rest of
the suite uses: the point is to exercise what an attacker's browser would
actually send, which is a request without the double-submit header.
"""

import pytest
from fastapi.testclient import TestClient

from app.auth import SESSION_COOKIE_NAME
from app.database import db_connection, initialize_database
from app.main import app
from app.security import CSRF_COOKIE_NAME, SECURITY_HEADERS
from app.settings import settings

SIGNUP = {"email": "owner@example.com", "password": "password123", "name": "Owner"}


@pytest.fixture
def raw_client(tmp_path):
    """A client that does *not* add the CSRF header automatically."""
    settings.database_url = f"sqlite:///{tmp_path / 'test.db'}"
    initialize_database()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def production_client(tmp_path):
    """Production settings, over https — a `Secure` cookie sent to an http
    origin is discarded by the client, so the base URL has to match the
    deployment this flag exists for.
    """
    settings.database_url = f"sqlite:///{tmp_path / 'test.db'}"
    settings.environment = "production"
    initialize_database()
    try:
        with TestClient(app, base_url="https://testserver") as test_client:
            yield test_client
    finally:
        settings.environment = "development"


def csrf_token(client: TestClient) -> str:
    client.get("/api/health")
    return client.cookies[CSRF_COOKIE_NAME]


def test_safe_request_issues_a_csrf_cookie(raw_client: TestClient) -> None:
    response = raw_client.get("/api/health")

    assert response.status_code == 200
    assert CSRF_COOKIE_NAME in raw_client.cookies
    # The frontend has to read it back to echo it in the header.
    assert "httponly" not in response.headers["set-cookie"].lower()


def test_unsafe_request_without_the_csrf_header_is_rejected(raw_client: TestClient) -> None:
    csrf_token(raw_client)

    response = raw_client.post("/api/v2/auth/signup", json=SIGNUP)

    assert response.status_code == 403
    assert response.json()["error"]["message"] == "CSRF token missing or invalid"


def test_unsafe_request_with_a_mismatched_token_is_rejected(raw_client: TestClient) -> None:
    csrf_token(raw_client)

    response = raw_client.post(
        "/api/v2/auth/signup",
        json=SIGNUP,
        headers={"X-CSRF-Token": "not-the-cookie-value"},
    )

    assert response.status_code == 403


def test_unsafe_request_with_no_cookie_at_all_is_rejected_and_seeded(
    raw_client: TestClient,
) -> None:
    """The header alone proves nothing — an attacker can set a header value on
    a request they craft. It has to match a cookie only the real origin can
    read, and a client with no cookie yet gets one so the retry can succeed.
    """
    response = raw_client.post(
        "/api/v2/auth/signup",
        json=SIGNUP,
        headers={"X-CSRF-Token": "invented"},
    )

    assert response.status_code == 403
    assert CSRF_COOKIE_NAME in raw_client.cookies


def test_unsafe_request_with_the_matching_pair_succeeds(raw_client: TestClient) -> None:
    token = csrf_token(raw_client)

    response = raw_client.post("/api/v2/auth/signup", json=SIGNUP, headers={"X-CSRF-Token": token})

    assert response.status_code == 201


def test_csrf_rejection_still_carries_the_security_headers(raw_client: TestClient) -> None:
    response = raw_client.post("/api/v2/auth/signup", json=SIGNUP)

    assert response.status_code == 403
    for header, value in SECURITY_HEADERS.items():
        assert response.headers[header] == value


def test_security_headers_are_present_on_api_and_page_responses(raw_client: TestClient) -> None:
    for path in ("/api/health", "/"):
        response = raw_client.get(path)
        for header, value in SECURITY_HEADERS.items():
            assert response.headers[header] == value, path

    policy = raw_client.get("/api/health").headers["content-security-policy"]
    assert "frame-ancestors 'none'" in policy
    assert "default-src 'self'" in policy


def test_session_cookie_is_httponly_and_not_secure_outside_production(
    raw_client: TestClient,
) -> None:
    token = csrf_token(raw_client)

    response = raw_client.post("/api/v2/auth/signup", json=SIGNUP, headers={"X-CSRF-Token": token})

    session_cookie = next(
        value
        for value in response.headers.get_list("set-cookie")
        if value.startswith(SESSION_COOKIE_NAME)
    )
    assert "HttpOnly" in session_cookie
    assert "Secure" not in session_cookie


def test_cookies_are_secure_in_production(production_client: TestClient) -> None:
    token = csrf_token(production_client)

    response = production_client.post(
        "/api/v2/auth/signup", json=SIGNUP, headers={"X-CSRF-Token": token}
    )

    assert response.status_code == 201

    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(value for value in cookies if value.startswith(SESSION_COOKIE_NAME))
    csrf_cookie = next(value for value in cookies if value.startswith(CSRF_COOKIE_NAME))
    assert "Secure" in session_cookie
    assert "Secure" in csrf_cookie


def test_login_rotates_the_session_and_invalidates_the_old_one(client: TestClient) -> None:
    client.post("/api/v2/auth/signup", json=SIGNUP)
    first_session = client.cookies[SESSION_COOKIE_NAME]

    client.post(
        "/api/v2/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]}
    )
    second_session = client.cookies[SESSION_COOKIE_NAME]

    assert second_session != first_session
    with db_connection() as connection:
        remaining = connection.execute("SELECT id FROM sessions").fetchall()
    assert [row["id"] for row in remaining] == [second_session]


def test_logout_deletes_the_session_row(client: TestClient) -> None:
    client.post("/api/v2/auth/signup", json=SIGNUP)

    client.post("/api/v2/auth/logout")

    with db_connection() as connection:
        assert connection.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"] == 0
