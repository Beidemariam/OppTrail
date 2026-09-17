import socket
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.database import initialize_database
from app.main import app
from app.rate_limit import auth_rate_limiter
from app.security import CSRF_COOKIE_NAME, SAFE_METHODS
from app.settings import settings


class CsrfClient(TestClient):
    """A test client that behaves like the browser the app is written for.

    Every unsafe request needs the double-submit CSRF pair (`app/security.py`);
    a real browser picks the cookie up on first page load and the frontend
    echoes it in the header. Doing the same here keeps the whole suite running
    against the production middleware stack rather than around it.
    `tests/test_security.py` uses a plain `TestClient` to prove the middleware
    still rejects a request without the pair.
    """

    def request(self, method: str, url: Any, **kwargs: Any) -> Any:
        if method.upper() not in SAFE_METHODS:
            if CSRF_COOKIE_NAME not in self.cookies:
                super().request("GET", "/api/health")
            headers = dict(kwargs.pop("headers", None) or {})
            headers.setdefault("X-CSRF-Token", self.cookies[CSRF_COOKIE_NAME])
            kwargs["headers"] = headers
        return super().request(method, url, **kwargs)


# Loopback stays reachable because that is where the tests' own machinery
# lives; anything else is a real outbound call and must not happen in a unit or
# integration test (brief §6.5).
LOCAL_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", ""})


@pytest.fixture(autouse=True)
def no_live_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any test that opens a socket to somewhere off this machine.

    Without this the suite's OpenAI mocking is a convention: forget one
    `monkeypatch.setattr` and the test quietly bills a real API call and starts
    depending on the network. The guard turns that into an immediate,
    attributable failure. `TestClient` talks to the app in-process over ASGI
    and opens no socket at all, so nothing legitimate is caught here.
    """
    real_connect = socket.socket.connect

    def guarded_connect(self: socket.socket, address: Any) -> Any:
        host = address[0] if isinstance(address, tuple) else address
        if isinstance(host, str) and host not in LOCAL_HOSTS:
            raise RuntimeError(
                f"Live network access to {host!r} from a test. Mock the client "
                "instead (brief §6.5: no live network in tests)."
            )
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)


@pytest.fixture(autouse=True)
def reset_rate_limiter() -> Iterator[None]:
    """The limiter is process-global by design (`app/rate_limit.py`), so it has
    to be cleared between tests or one test's signups would exhaust another's
    budget — an order dependence brief §6.5 forbids.
    """
    auth_rate_limiter.reset()
    yield
    auth_rate_limiter.reset()


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    settings.database_url = f"sqlite:///{tmp_path / 'test.db'}"
    initialize_database()
    with CsrfClient(app) as test_client:
        yield test_client
