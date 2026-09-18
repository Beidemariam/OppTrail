"""Rebuild the FTS5 search index (ADR 0007, Makefile target `make reindex`).

The index is maintained by triggers, so an ordinary installation never needs
this. It exists for the two cases the ADR names: a corrupted index, and a
schema change — a different tokenizer, or a new kind of indexed document —
after which the stored terms no longer match what a query produces.

It is safe to run at any time: the rebuild happens in one transaction, and a
reader mid-query sees either the old index or the new one.
"""

from __future__ import annotations

from app.database import db_connection, sqlite_path_from_url
from app.search import rebuild_search_index
from app.settings import settings


def reindex() -> int:
    with db_connection() as connection:
        indexed = rebuild_search_index(connection)
        connection.commit()
    return indexed


def main() -> int:
    indexed = reindex()
    print(f"Reindexed {indexed} documents in {sqlite_path_from_url(settings.database_url)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
