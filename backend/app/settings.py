from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./app.db"
    # Who may define a custom field or write an automation rule (R.1c,
    # **D-215**, the reviewer's ruling at the Phase R gate: *"both have to be
    # done by the owner"*). Comma-separated email addresses.
    #
    # These two writes were open to every signed-in caller, because
    # `FEATURES.md` says "admin-defined" and this app had no admin (D-171,
    # D-173). They are the widest surfaces in the application and both are
    # global rather than scoped to a deal, so "the owner" cannot mean an
    # opportunity's owner: there is no opportunity in sight when you define a
    # field that lands on every deal.
    #
    # **Configuration rather than a column**, which is a deliberate departure
    # from the "flag on users" shape the ruling named. The two are
    # indistinguishable to a reader -- neither offers an in-app way to grant
    # admin, which nobody asked for -- and this way there is no migration, no
    # second source of truth to drift from the environment, and no state to
    # repair if the list changes. `permissions.is_admin` is the whole
    # implementation. If granting it in the app is ever wanted, a column is an
    # additive migration and this list becomes its seed.
    #
    # Empty means **nobody**, which is the safe default for a fresh install
    # and the loud one: the screens say who to ask rather than failing a form.
    admin_emails: str = ""
    frontend_static_dir: str = "../frontend/out"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6-luna"
    # Applied to the OpenAI client itself (`ai_service.ask_openai`), so a hung
    # or flaky call fails the request instead of hanging it indefinitely.
    # `max_retries` uses the SDK's own backoff, not a hand-rolled retry loop.
    #
    # Sized by measurement, not by guess (D-168). A reasoning model's floor
    # latency is tens of seconds before it has thought about anything: the
    # shipped 20.0 was below it, so every call failed three times and answered
    # 502 after a minute. Measured against the development data at
    # `openai_reasoning_effort = "low"`: ~29s for a two-entry timeline, 40.1s
    # for a 41-entry one. 90.0 clears that with headroom for a longer deal.
    # One retry rather than two, because the retry that matters here is for a
    # transient 429 or 5xx and a timeout retry only multiplies the wait a
    # reader is already sitting through.
    openai_timeout_seconds: float = 90.0
    openai_max_retries: int = 1
    # How hard the model thinks before answering. Load bearing for latency:
    # unset, a reasoning model spends thousands of reasoning tokens
    # summarizing a short timeline (measured: 2176-4480 tokens, 65-105s)
    # where "low" spends a few hundred in ~30s and answers at least as fully.
    # Empty string omits the parameter entirely, which is what a
    # non-reasoning `openai_model` needs - the Responses API rejects
    # `reasoning` outright for those, so this cannot be hardcoded.
    openai_reasoning_effort: str = "low"
    # The forecast's stage ramp (milestone 6.2, `docs/FEATURES.md` §10 asks
    # for "configurable probabilities"). A JSON object of stage name to a
    # number between 0 and 1; any stage left out keeps
    # `dashboard.DEFAULT_FORECAST_PROBABILITIES`, so a deployment can tune two
    # stages without restating the other five. The right ramp is a property of
    # a sales process rather than of this software, which is why it is
    # configuration and not a constant.
    forecast_probabilities: dict[str, float] = {}
    environment: str = "development"
    # Attempts per source address per window, applied to login and signup
    # separately (`rate_limit.py`). Sized so a normal human never meets it and
    # a credential-stuffing run does.
    auth_rate_limit_attempts: int = 20
    auth_rate_limit_window_seconds: int = 300
    # 10 MiB, the cap ADR 0008 names. Read by `uploads.validate_upload`, which
    # `routes_attachments.py` is the first caller of (milestone 4.3).
    max_upload_bytes: int = 10 * 1024 * 1024
    # `None` means "next to the database file" (`uploads.attachments_dir()`),
    # the same default `backup_dir` takes: ADR 0008's blobs live under the same
    # `/data` volume as the database they belong to.
    attachments_dir: str | None = None
    # ADR 0003's live-update stream. A connection is closed deliberately after
    # `sse_max_connection_seconds` and the browser's own `EventSource`
    # reconnects (`app/events.py`), so an intermediary never gets to reap a
    # connection this app has forgotten about; the heartbeat is the comment
    # line that keeps it from looking idle in the meantime.
    sse_max_connection_seconds: float = 300.0
    sse_heartbeat_seconds: float = 15.0
    # `None` means "next to the database file" (`backup.backup_dir()`); ADR
    # 0011's snapshots live under the same `/data` volume so they survive a
    # container recreate without a second mount.
    backup_dir: str | None = None
    backup_retention_count: int = 7
    # ADR 0004's in-process scheduler (milestone 6.5). Off in the test suite,
    # which sets it directly: a scheduler ticking under a test would fire a
    # rule the test just wrote and the failure would land somewhere else.
    scheduler_enabled: bool = True
    # How often the time-driven triggers are evaluated -- `no_activity` and
    # `close_date_approaching`, which are the two of §11's five that the clock
    # owns. Fifteen minutes rather than a minute because both are measured in
    # days: a rule about fourteen days of silence does not become wrong
    # fourteen minutes late, and a tick walks every enabled rule.
    automation_interval_minutes: int = 15
    # ADR 0011's snapshot, finally on a schedule rather than waiting for
    # somebody to type `make backup`. Daily, which is what
    # `backup_retention_count = 7` already assumed when it kept a week.
    backup_interval_hours: int = 24

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
        "backup_retention_count",
    )
    @classmethod
    def _must_be_positive(cls, value: int, info: ValidationInfo) -> int:
        if value <= 0:
            raise ValueError(f"{str(info.field_name).upper()} must be greater than 0, got: {value}")
        return value

    @field_validator(
        "openai_timeout_seconds",
        "sse_max_connection_seconds",
        "sse_heartbeat_seconds",
    )
    @classmethod
    def _seconds_must_be_positive(cls, value: float, info: ValidationInfo) -> float:
        if value <= 0:
            raise ValueError(f"{str(info.field_name).upper()} must be greater than 0, got: {value}")
        return value

    @field_validator("forecast_probabilities")
    @classmethod
    def _probabilities_must_be_fractions(cls, value: dict[str, float]) -> dict[str, float]:
        for stage, probability in value.items():
            if not 0.0 <= probability <= 1.0:
                raise ValueError(
                    "FORECAST_PROBABILITIES values must be between 0 and 1, "
                    f"got {probability} for {stage!r}"
                )
        return value

    @field_validator("openai_reasoning_effort")
    @classmethod
    def _openai_reasoning_effort_must_be_known(cls, value: str) -> str:
        allowed = ("", "minimal", "low", "medium", "high")
        if value not in allowed:
            raise ValueError(
                "OPENAI_REASONING_EFFORT must be one of "
                f"{', '.join(repr(option) for option in allowed)}, got: {value!r}"
            )
        return value

    @field_validator("openai_max_retries")
    @classmethod
    def _openai_max_retries_must_not_be_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError(f"OPENAI_MAX_RETRIES must be 0 or greater, got: {value}")
        return value


settings = Settings()
