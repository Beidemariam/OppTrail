from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./app.db"
    frontend_static_dir: str = "../frontend/out"
    openai_api_key: str | None = None
    session_secret: str = "dev-only-change-me"

    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")


settings = Settings()
