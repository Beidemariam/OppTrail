"""The 14-day rule, in one place (milestone R.3).

"Nothing has happened on this deal for a fortnight" is asked in two shapes —
*is this one stalled* on a card, and *which of these are* on the dashboard —
and until R.3 each shape carried its own copy of a three-way union over
entries, notes and comments. `dashboard.py`'s own comment said so: "One
definition would be better than two."

Unifying them is also the performance fix, which is why it lands here rather
than as tidying. `GET /api/v2/opportunities` asked the per-card version **once
per row**, so a page of 50 ran 50 unions; at `AGENTS.md`'s confirmed scale
that measured 63 ms a page and 448 ms for the eight pages the board actually
reads (the frontend walks every page: D-093). Rewriting it as one grouped pass
over the page's ids changed nothing — **55 ms** — because the cost is the
240,000 note and comment rows the union walks, not the number of statements.

So the answer is not a better query. Revision `0022_last_activity` maintains
`opportunities.last_activity_at` with triggers and this module reads it: a
board page is **4 ms**, and the rule is still derived from exactly the same
definition of activity, written once in the revision that owns the triggers.
"""

import sqlite3
from collections.abc import Sequence

from .time_utils import utc_days_ago

#: A deal nothing has happened on for this long reads as stalled. One
#: definition, read by the board, a single deal's own screen and the
#: dashboard's stalled list.
STALLED_AFTER_DAYS = 14


def stalled_opportunity_ids(
    connection: sqlite3.Connection,
    opportunity_ids: Sequence[int],
) -> set[int]:
    """Which of these deals have had nothing happen for `STALLED_AFTER_DAYS`.

    One indexed read of a column the schema maintains, rather than the union
    this used to compute: revision `0022_last_activity` keeps
    `opportunities.last_activity_at` in step through triggers, for the reason
    the FTS index is maintained the same way — a write path added later cannot
    forget to call something it never knew about.

    A deal with no activity at all is **not** stalled. Its column is `NULL`,
    which no comparison satisfies, so it falls out of the answer by itself —
    the same result the union gave when its `MAX` came back `NULL`.
    """
    if not opportunity_ids:
        return set()

    ids = list(opportunity_ids)
    rows = connection.execute(
        f"""
        SELECT id
        FROM opportunities
        WHERE id IN ({", ".join("?" for _ in ids)})
            AND deleted_at IS NULL
            AND last_activity_at IS NOT NULL
            AND last_activity_at < ?
        """,
        (*ids, utc_days_ago(STALLED_AFTER_DAYS)),
    ).fetchall()
    return {int(row["id"]) for row in rows}


def is_opportunity_stalled(connection: sqlite3.Connection, opportunity_id: int) -> bool:
    """The same question about one deal, for the five routes that answer with
    one — a thin wrapper rather than a second query, so there is nothing to
    drift."""
    return opportunity_id in stalled_opportunity_ids(connection, (opportunity_id,))
