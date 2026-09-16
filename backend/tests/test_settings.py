import pytest
from pydantic import ValidationError

from app.settings import Settings


def test_database_url_must_be_sqlite() -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL must start with"):
        Settings(database_url="postgresql://localhost/db")


def test_environment_must_be_a_known_value() -> None:
    with pytest.raises(ValidationError, match="ENVIRONMENT must be one of"):
        Settings(environment="staging")


def test_valid_settings_construct_without_error() -> None:
    settings = Settings(database_url="sqlite:///./x.db", environment="production")
    assert settings.database_url == "sqlite:///./x.db"
    assert settings.environment == "production"
