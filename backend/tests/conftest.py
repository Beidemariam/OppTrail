from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.database import initialize_database
from app.main import app
from app.settings import settings


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    settings.database_url = f"sqlite:///{tmp_path / 'test.db'}"
    initialize_database()
    with TestClient(app) as test_client:
        yield test_client
