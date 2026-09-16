from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./app.db"
    frontend_static_dir: str = "../frontend/out"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6-luna"
    environment: str = "development"

    model_config = SettingsConfigDict(env_file="../.env", extra="ignore", validate_assignment=True)

    @field_validator("database_url")
    @classmethod
    def _database_url_must_be_sqlite(cls, value: str) -> str:
        if not value.startswith("sqlite:///"):
            raise ValueError(f"DATABASE_URL must start with 'sqlite:///', got: {value!r}")
        return value

    @field_validator("environment")
    @classmethod
    def _environment_must_be_known(cls, value: str) -> str:
        allowed = {"development", "production", "test"}
        if value not in allowed:
            raise ValueError(f"ENVIRONMENT must be one of {sorted(allowed)}, got: {value!r}")
        return value


settings = Settings()
