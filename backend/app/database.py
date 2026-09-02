from pathlib import Path
import sqlite3

from .settings import settings


def sqlite_path_from_url(database_url: str) -> Path:
    if not database_url.startswith("sqlite:///"):
        raise ValueError("DATABASE_URL must use sqlite:/// for the MVP")

    raw_path = database_url.removeprefix("sqlite:///")
    return Path(raw_path).expanduser()


def initialize_database() -> None:
    database_path = sqlite_path_from_url(settings.database_url)
    if database_path.parent != Path("."):
        database_path.parent.mkdir(parents=True, exist_ok=True)

    schema_path = Path(__file__).resolve().parent / "schema.sql"
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(schema_path.read_text(encoding="utf-8"))
