from datetime import UTC, datetime, timedelta

# Fixed-width UTC ISO-8601. Every timestamp the app writes uses this format so
# that lexicographic ordering in SQLite is also chronological ordering.
CANONICAL_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
SQLITE_CANONICAL_NOW = "strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"


def utc_now() -> str:
    return datetime.now(UTC).strftime(CANONICAL_FORMAT)


def to_canonical(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime(CANONICAL_FORMAT)


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp, treating a missing offset as UTC."""
    parsed = datetime.fromisoformat(value.replace(" ", "T"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def utc_days_ago(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).strftime(CANONICAL_FORMAT)
