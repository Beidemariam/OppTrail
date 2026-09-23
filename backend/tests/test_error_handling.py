import contextlib
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app import routes_opportunities
from app.logging_utils import REQUEST_ID_HEADER
from app.settings import settings


@contextlib.contextmanager
def server_exceptions_not_raised(client: TestClient) -> Iterator[None]:
    """`raise_server_exceptions=True` is the shared `client` fixture's default
    (and the suite's default generally), so a genuine bug surfaces as a loud
    test failure elsewhere. These two tests need the opposite so they can
    inspect the JSON body our handler sends before Starlette's
    `ServerErrorMiddleware` re-raises for the test client's benefit — flip the
    flag on the existing transport rather than opening a second `TestClient`,
    which showed unrelated order-dependent flakiness from running two anyio
    portals against the same app in one process.
    """
    transport = client._transport  # type: ignore[attr-defined]
    original = transport.raise_server_exceptions
    transport.raise_server_exceptions = False
    try:
        yield
    finally:
        transport.raise_server_exceptions = original


def signup(client: TestClient, email: str = "owner@example.com") -> None:
    response = client.post(
        "/api/v2/auth/signup",
        json={"email": email, "password": "password123", "name": "Owner"},
    )
    assert response.status_code == 201


def create_opportunity(client: TestClient) -> None:
    response = client.post(
        "/api/v2/opportunities",
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


def test_unhandled_exception_returns_json_detail_envelope(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression test for the API error envelope gap: before `errors.py`'s
    handler was registered, an unhandled exception fell through to Starlette's
    default plain-text 500, which broke `apiRequest<T>()`'s `response.json()`
    parse (CLAUDE.md: it throws on non-2xx using the message in the envelope).
    """
    signup(client)
    create_opportunity(client)

    def explode(*_args: object, **_kwargs: object) -> bool:
        raise RuntimeError("boom")

    monkeypatch.setattr(routes_opportunities, "is_opportunity_stalled", explode)

    with server_exceptions_not_raised(client):
        response = client.get("/api/v2/opportunities")

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"error": {"code": "internal_error", "message": "boom"}}
    assert REQUEST_ID_HEADER in response.headers


def test_unhandled_exception_hides_details_in_production(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    signup(client)
    create_opportunity(client)

    def explode(*_args: object, **_kwargs: object) -> bool:
        raise RuntimeError("boom")

    monkeypatch.setattr(routes_opportunities, "is_opportunity_stalled", explode)
    monkeypatch.setattr(settings, "environment", "production")

    with server_exceptions_not_raised(client):
        response = client.get("/api/v2/opportunities")

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "Internal server error"}
    }


def test_the_envelope_is_the_api_s_and_not_the_whole_server_s(client: TestClient) -> None:
    """`errors.py`'s handlers are registered app-wide, but this process also
    serves the exported SPA. A failure on a page path is a web-server failure
    and keeps FastAPI's own shape -- the `{"error": ...}` envelope describes
    the API, which is the thing a client parses (`is_api_path`).
    """
    response = client.post("/some/page")

    assert response.status_code == 405
    assert response.json() == {"detail": "Method Not Allowed"}
