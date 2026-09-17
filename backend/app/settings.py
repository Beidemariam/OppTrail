from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./app.db"
    frontend_static_dir: str = "../frontend/out"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6-luna"
    # Applied to the OpenAI client itself (`ai_service.ask_openai`), so a hung
    # or flaky call fails the request instead of hanging it indefinitely.
    # `max_retries` uses the SDK's own backoff, not a hand-rolled retry loop.
    openai_timeout_seconds: float = 20.0
    openai_max_retries: int = 2
    environment: str = "development"
    # Attempts per source address per window, applied to login and signup
    # separately (`rate_limit.py`). Sized so a normal human never meets it and
    # a credential-stuffing run does.
    auth_rate_limit_attempts: int = 20
    auth_rate_limit_window_seconds: int = 300
    # 10 MiB. No endpoint accepts a file yet; `uploads.py` explains why the
    # limit is defined now.
    max_upload_bytes: int = 10 * 1024 * 1024

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

    @field_validator(
        "auth_rate_limit_attempts",
        "auth_rate_limit_window_seconds",
        "max_upload_bytes",
    )
    @classmethod
    def _must_be_positive(cls, value: int, info: ValidationInfo) -> int:
        if value <= 0:
            raise ValueError(f"{str(info.field_name).upper()} must be greater than 0, got: {value}")
        return value

    @field_validator("openai_timeout_seconds")
    @classmethod
    def _openai_timeout_must_be_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError(f"OPENAI_TIMEOUT_SECONDS must be greater than 0, got: {value}")
        return value

    @field_validator("openai_max_retries")
    @classmethod
    def _openai_max_retries_must_not_be_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError(f"OPENAI_MAX_RETRIES must be 0 or greater, got: {value}")
        return value


settings = Settings()
