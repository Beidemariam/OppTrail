import sqlite3

from .permissions import visible_entries_clause
from .time_utils import utc_now

# An entry's number within its own opportunity (milestone 3.9, **D-139**).
#
# The AI cites entries by number and the timeline prints one on every card, so
# both have to mean the same thing -- which is why this is one SQL expression
# read by `routes_timeline.ENTRY_ROWS_SQL` and by
# `ai_service.build_timeline_context` rather than a rule each side implements.
#
# **Chronological, not creation order.** #1 is the oldest thing that happened
# on the deal, because that is what a person counting a timeline counts.
# Creation order was the alternative and is visibly wrong on imported data: a
# deal whose 32 events were backdated in one batch gets its three system
# entries numbered #1-#3 and its earliest real event #4. Ordered by
# `(event_timestamp, id)`, the same pair the timeline list orders and pages by,
# so the numbers ascend exactly as the oldest-first reading does and ties
# between two entries stamped in the same second resolve the same way in both.
#
# The cost is stated in D-139: inserting a *backdated* entry renumbers
# everything after it, so this number is a reading aid and never an identity.
# The identity is the row id, which is what `?entry=` links carry (D-124).
#
# **It counts what the reader may read** (R.1c, **D-209**). A sealed entry is
# absent from everybody else's timeline rather than emptied in place, and a
# number that counted it anyway would leave a gap where it used to stand --
# which tells the reader precisely what the removed card used to tell them.
# The cost is the other half of D-139's own framing: two people may call one
# entry by two numbers, which is tolerable exactly because this was never an
# identity. Both halves of a single reader's view agree, which is what
# matters: the card they see and the number the AI cites are this one
# expression, and the AI's context has been assembled per reader since R.1b.
#
# **It carries one bound parameter -- the reader's id -- and it sits in the
# SELECT list**, so it binds *before* anything in the embedding query's
# `WHERE`. Every caller passes `reader_id` first; `ENTRY_ROWS_SQL` says so
# again where it is used.
ENTRY_SEQUENCE_SQL = f"""(
        SELECT COUNT(*)
        FROM timeline_entries AS sequence_peers
        WHERE sequence_peers.opportunity_id = timeline_entries.opportunity_id
            AND sequence_peers.deleted_at IS NULL
            AND {visible_entries_clause("sequence_peers")}
            AND (sequence_peers.event_timestamp, sequence_peers.id)
                <= (timeline_entries.event_timestamp, timeline_entries.id)
    )"""


def create_system_timeline_entry(
    connection: sqlite3.Connection,
    opportunity_id: int,
    created_by: int,
    entry_type: str,
    title: str,
    body: str,
) -> None:
    now = utc_now()
    connection.execute(
        """
        INSERT INTO timeline_entries (
            opportunity_id,
            type,
            title,
            body,
            event_timestamp,
            created_by,
            system_generated,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 1, ?)
        """,
        (opportunity_id, entry_type, title, body, now, created_by, now),
    )
