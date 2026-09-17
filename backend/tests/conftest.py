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
