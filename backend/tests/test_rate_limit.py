"""Rate limiting on the unauthenticated auth endpoints (brief §4.5).

Time is injected rather than slept through, per brief §6.5.
"""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.rate_limit import SWEEP_THRESHOLD, RateLimiter, client_key
from app.settings import settings

SIGNUP = {"email": "owner@example.com", "password": "password123", "name": "Owner"}


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def tight_limit():
    """Three attempts per minute, so the tests read as intent, not arithmetic."""
    attempts = settings.auth_rate_limit_attempts
    window = settings.auth_rate_limit_window_seconds
    settings.auth_rate_limit_attempts = 3
    settings.auth_rate_limit_window_seconds = 60
    yield
    settings.auth_rate_limit_attempts = attempts
    settings.auth_rate_limit_window_seconds = window


def test_attempts_within_the_window_are_capped() -> None:
    clock = FakeClock()
    limiter = RateLimiter(clock)

    for _ in range(3):
        limiter.check("login:1.2.3.4", 3, 60)

    with pytest.raises(HTTPException) as excinfo:
        limiter.check("login:1.2.3.4", 3, 60)

    assert excinfo.value.status_code == 429
    assert excinfo.value.headers == {"Retry-After": "61"}


def test_the_window_slides_rather_than_resetting() -> None:
    clock = FakeClock()
    limiter = RateLimiter(clock)
    for _ in range(3):
        limiter.check("login:1.2.3.4", 3, 60)

    # Half a window later the oldest attempts are still inside it.
    clock.advance(30)
    with pytest.raises(HTTPException):
        limiter.check("login:1.2.3.4", 3, 60)

    # Once they age out, the budget is available again.
    clock.advance(31)
    limiter.check("login:1.2.3.4", 3, 60)


def test_callers_and_endpoints_are_counted_separately() -> None:
    clock = FakeClock()
    limiter = RateLimiter(clock)
    for _ in range(3):
        limiter.check("login:1.2.3.4", 3, 60)

    limiter.check("login:5.6.7.8", 3, 60)
    limiter.check("signup:1.2.3.4", 3, 60)


def test_reset_clears_every_counter() -> None:
    limiter = RateLimiter(FakeClock())
    for _ in range(3):
        limiter.check("login:1.2.3.4", 3, 60)

    limiter.reset()

    limiter.check("login:1.2.3.4", 3, 60)


def test_expired_keys_are_swept_so_the_dict_cannot_grow_without_bound() -> None:
    clock = FakeClock()
    limiter = RateLimiter(clock)
    for index in range(SWEEP_THRESHOLD):
        limiter.check(f"login:10.0.0.{index}", 3, 60)

    clock.advance(61)
    limiter.check("login:fresh", 3, 60)

    assert limiter._hits.keys() == {"login:fresh"}


def test_client_key_falls_back_when_the_transport_reports_no_peer() -> None:
    request = Request({"type": "http", "headers": [], "client": None})

    assert client_key(request, "login") == "login:unknown"


def test_login_is_rate_limited(client: TestClient, tight_limit: None) -> None:
    client.post("/api/v2/auth/signup", json=SIGNUP)
    client.post("/api/v2/auth/logout")
    credentials = {"email": SIGNUP["email"], "password": "wrong-password"}

    for _ in range(3):
        assert client.post("/api/v2/auth/login", json=credentials).status_code == 401

    blocked = client.post("/api/v2/auth/login", json=credentials)

    assert blocked.status_code == 429
    assert blocked.json()["error"]["message"] == "Too many attempts. Try again later."
    assert "Retry-After" in blocked.headers


def test_signup_is_rate_limited_independently_of_login(
    client: TestClient, tight_limit: None
) -> None:
    for index in range(3):
        response = client.post(
            "/api/v2/auth/signup",
            json={**SIGNUP, "email": f"user{index}@example.com"},
        )
        assert response.status_code == 201
        client.post("/api/v2/auth/logout")

    blocked = client.post("/api/v2/auth/signup", json={**SIGNUP, "email": "user4@example.com"})
    assert blocked.status_code == 429

    # The login budget is untouched by the signup flood.
    allowed = client.post(
        "/api/v2/auth/login",
        json={"email": "user0@example.com", "password": SIGNUP["password"]},
    )
    assert allowed.status_code == 200


def test_the_limit_is_checked_before_the_password_is_verified(
    client: TestClient, tight_limit: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A blocked caller must not reach bcrypt — otherwise the limiter protects
    the account but not the CPU, and the endpoint stays a denial-of-service
    amplifier.
    """
    client.post("/api/v2/auth/signup", json=SIGNUP)
    client.post("/api/v2/auth/logout")
    credentials = {"email": SIGNUP["email"], "password": "wrong-password"}
    for _ in range(3):
        client.post("/api/v2/auth/login", json=credentials)

    def fail_if_called(*args: object, **kwargs: object) -> bool:
        raise AssertionError("password verification ran for a rate-limited request")

    monkeypatch.setattr("app.routes_auth.verify_password", fail_if_called)

    assert client.post("/api/v2/auth/login", json=credentials).status_code == 429
