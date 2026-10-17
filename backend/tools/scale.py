"""The corpus this app is sized for, built in one place (milestone R.3).

`AGENTS.md`'s Confirmed Scale is the single most important constraint in the
project: **20 users, 400 opportunities, ~200 entries each, 2-3 concurrent —
roughly 800,000 rows.** It is the figure every "no Postgres, no broker, no job
queue" decision was argued against, and until R.3 only one test had ever built
anything like it (milestone 6.2's dashboard budget, **D-172**).

This module is that builder, with dials rather than two near-copies:

- `build_scale_corpus(connection, opportunities=…, entries=…)` is 6.2's
  corpus exactly — same rows, same spread, same values — because D-172's
  measurements are tied to it and a corpus that drifts invalidates them.
- The keyword arguments beyond those two add what a *read* path meets and an
  aggregate does not: other people (`readers`), deals shared with them
  (`shares`), entries one of them has sealed (`private_every`, R.1b), tasks,
  and the notification rows a timeline of this size leaves in people's
  inboxes.

Inserted through `executemany` on the real schema, so the FTS5 triggers fire
and the search index is built the way a running database builds it — which is
most of the 136 MB, and the thing search performance is actually about.
"""

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.time_utils import utc_now

#: Every table user data lands in, for the row count a corpus reports.
COUNTED_TABLES = (
    "users",
    "opportunities",
    "opportunity_shares",
    "timeline_entries",
    "notes",
    "comments",
    "tasks",
    "notifications",
    "opportunity_versions",
    "timeline_entry_versions",
    "note_versions",
    "task_versions",
    "audit_log_entries",
)

STAGES = ["Prospecting", "Qualification", "Proposal", "Negotiation", "Closed Won"]
STAMP = "%Y-%m-%dT%H:%M:%SZ"


@dataclass(frozen=True)
class ScaleFacts:
    """What was built, so a test can report it rather than assert a guess."""

    rows: int
    per_table: dict[str, int]
    opportunities: int
    entries: int

    def summary(self) -> str:
        biggest = sorted(self.per_table.items(), key=lambda row: -row[1])[:5]
        return f"{self.rows:,} rows (" + ", ".join(f"{t} {n:,}" for t, n in biggest) + ")"


def build_scale_corpus(
    connection: sqlite3.Connection,
    *,
    opportunities: int,
    entries: int,
    readers: int = 6,
    shares: bool = False,
    private_every: int = 0,
    notes: int | None = None,
    comments: int | None = None,
    tasks: int = 0,
    notifications: int = 0,
) -> ScaleFacts:
    """Fill a database with a corpus of the given size.

    Spread across two years rather than all stamped now, because that is what
    a database holding this many rows looks like and because several reads ask
    for a *window* of it — a fixture with every row inside that window
    measures something no deployment will ever ask.

    **Composable with rows that are already there** (R.7). Every id below is
    relative to what the database already holds, so this runs on an empty
    database for `tests/test_performance.py` and on top of `make seed`'s demo
    rows for `make seed --scale`. Without that, a generated note would attach
    itself to one of the five deals a person is about to read.

    The first user owns every generated opportunity — user 1 on an empty
    database, Alex after a demo seed — so a read as the owner is the widest
    possible answer; `shares` adds the rows that make the same read a
    permission-filtered one for everybody else.
    """
    base = datetime.now(UTC) - timedelta(days=730)
    now = utc_now()

    def spread(index: int, total: int) -> str:
        return (base + timedelta(seconds=int(730 * 86400 * index / max(total, 1)))).strftime(STAMP)

    def highest(table: str) -> int:
        row = connection.execute(f"SELECT COALESCE(MAX(id), 0) AS top FROM {table}").fetchone()
        return int(row["top"])

    first_user = highest("users")
    first_opportunity = highest("opportunities")
    first_entry = highest("timeline_entries")
    first_note = highest("notes")
    first_task = highest("tasks")
    owner = max(first_user, 1)

    def reader_id(index: int) -> int:
        return first_user + (index % readers) + 1

    connection.executemany(
        "INSERT INTO users (email, password_hash, name, created_at) VALUES (?, ?, ?, ?)",
        [
            (f"rep{first_user + rep}@example.com", "x", f"Rep {first_user + rep}", now)
            for rep in range(readers)
        ],
    )
    connection.executemany(
        """
        INSERT INTO opportunities
            (name, account_name, value, currency, stage, owner_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (f"Deal {i}", f"Account {i}", 1000 + i, "USD", STAGES[i % 5], owner, now, now)
            for i in range(opportunities)
        ],
    )

    if shares:
        # Each deal shared with two of the other readers, alternating role, so
        # a non-owner's read is filtered by `opportunity_shares` across a
        # realistic fraction of the board rather than all of it or none.
        connection.executemany(
            """
            INSERT INTO opportunity_shares
                (opportunity_id, user_id, role, invited_by, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    first_opportunity + deal + 1,
                    first_user + reader,
                    "editor" if (deal + offset) % 2 else "viewer",
                    owner,
                    now,
                )
                for deal in range(opportunities)
                for offset, reader in enumerate(
                    (2 + (deal % max(readers - 1, 1)), 2 + ((deal + 1) % max(readers - 1, 1)))
                )
                if reader <= readers
            ],
        )

    def visibility(index: int) -> str:
        return "private" if private_every and index % private_every == 0 else "shared"

    connection.executemany(
        """
        INSERT INTO timeline_entries
            (opportunity_id, type, title, body, event_timestamp, created_by, created_at,
             visibility)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                first_opportunity + (i % opportunities) + 1,
                "stage_change" if i % 500 == 0 else "call",
                "Stage changed to Proposal" if i % 500 == 0 else f"Entry {i}",
                "body",
                spread(i, entries),
                reader_id(i),
                spread(i, entries),
                visibility(i),
            )
            for i in range(entries)
        ],
    )

    # 6.2's corpus derives these from the entry count; R.3 passes its own,
    # because the row *mix* is what a read path meets and 800,000 rows made of
    # entries alone is not the database `AGENTS.md` describes.
    note_rows = entries // 4 if notes is None else notes
    comment_rows = entries // 12 if comments is None else comments
    connection.executemany(
        """
        INSERT INTO notes (entry_id, body, created_by, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                first_entry + (i % entries) + 1,
                "note",
                reader_id(i),
                spread(i, note_rows),
                now,
            )
            for i in range(note_rows)
        ],
    )
    connection.executemany(
        "INSERT INTO comments (note_id, body, created_by, created_at) VALUES (?, ?, ?, ?)",
        [
            (
                first_note + (i % note_rows) + 1,
                "comment",
                reader_id(i),
                spread(i, comment_rows),
            )
            for i in range(comment_rows)
        ],
    )

    if tasks:
        connection.executemany(
            """
            INSERT INTO tasks
                (opportunity_id, entry_id, title, due_date, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    first_opportunity + (i % opportunities) + 1,
                    first_entry + (i % entries) + 1,
                    f"Follow up {i}",
                    spread(i, tasks)[:10],
                    owner,
                    now,
                    now,
                )
                for i in range(tasks)
            ],
        )
        connection.executemany(
            "INSERT INTO task_assignees (task_id, user_id) VALUES (?, ?)",
            [(first_task + i + 1, reader_id(i)) for i in range(tasks)],
        )

    if notifications:
        # What a timeline this size leaves in an inbox. The payload shape is
        # `notification_service`'s own, because the inbox read parses it.
        connection.executemany(
            """
            INSERT INTO notifications (user_id, type, payload, read, created_at)
            VALUES (?, ?, ?, 0, ?)
            """,
            [
                (
                    reader_id(i),
                    "shared_activity",
                    (
                        '{"source_type": "entry", "source_id": '
                        f"{first_entry + (i % entries) + 1}"
                        ', "opportunity_id": '
                        f"{first_opportunity + (i % opportunities) + 1}"
                        ', "actor_id": ' + str(owner) + ', "title": "Entry"}'
                    ),
                    spread(i, notifications),
                )
                for i in range(notifications)
            ],
        )

    connection.commit()

    per_table = {}
    for table in COUNTED_TABLES:
        per_table[table] = connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    # A contentless FTS5 table cannot be counted without a MATCH, but its
    # docsize shadow table holds one row per indexed document — which is the
    # number that matters here, since that index is most of the 136 MB.
    per_table["search_index"] = connection.execute(
        "SELECT count(*) FROM search_index_docsize"
    ).fetchone()[0]

    return ScaleFacts(
        rows=sum(per_table.values()),
        per_table=per_table,
        opportunities=opportunities,
        entries=entries,
    )
