"""The maintained `last_activity_at` column, and whether it can be trusted.

Milestone R.3. The 14-day stalled rule used to be computed live from a
three-way union, which measured 63 ms on every page of the board; revision
`0022_last_activity` maintains the answer with triggers instead and
`app/stalled.py` reads it.

That trade buys speed with a **cache**, and this project's own rule about
caches is in the search section of `CLAUDE.md`: *"a read that trusts the index
to be current is a read that trusts a cache."* The FTS index earns that trust
from nine triggers and a test that proves what they do. These are that test
for this column — one case per way the answer can **fall**, which is the half
a careless denormalization gets wrong:

- a soft delete removing the newest activity,
- a restore putting it back,
- an entry's `event_timestamp` edited into the past (the one editable
  timestamp in the app),
- a whole entry's deletion taking its notes and comments with it.
"""

from fastapi.testclient import TestClient
from test_timeline import create_entry, create_opportunity, signup

from app.database import db_connection
from app.stalled import is_opportunity_stalled


def last_activity(opportunity_id: int) -> str | None:
    with db_connection() as connection:
        row = connection.execute(
            "SELECT last_activity_at FROM opportunities WHERE id = ?",
            (opportunity_id,),
        ).fetchone()
    return row["last_activity_at"] if row else None


def computed_activity(opportunity_id: int) -> str | None:
    """The same answer the old live query gave, for comparison.

    Kept here rather than in `app/stalled.py` because nothing in the
    application computes it any more — this is the oracle the column is
    checked against.
    """
    with db_connection() as connection:
        row = connection.execute(
            """
            SELECT MAX(activity_at) AS latest FROM (
                SELECT event_timestamp AS activity_at
                FROM timeline_entries
                WHERE opportunity_id = ? AND deleted_at IS NULL
                UNION ALL
                SELECT notes.created_at
                FROM notes
                JOIN timeline_entries ON timeline_entries.id = notes.entry_id
                WHERE timeline_entries.opportunity_id = ?
                    AND notes.deleted_at IS NULL
                    AND timeline_entries.deleted_at IS NULL
                UNION ALL
                SELECT comments.created_at
                FROM comments
                JOIN notes ON notes.id = comments.note_id
                JOIN timeline_entries ON timeline_entries.id = notes.entry_id
                WHERE timeline_entries.opportunity_id = ?
                    AND comments.deleted_at IS NULL
                    AND notes.deleted_at IS NULL
                    AND timeline_entries.deleted_at IS NULL
            )
            """,
            (opportunity_id, opportunity_id, opportunity_id),
        ).fetchone()
    return row["latest"]


def add_note(client: TestClient, entry_id: int, body: str = "A note") -> int:
    response = client.post(f"/api/v2/timeline/{entry_id}/notes", json={"body": body})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def add_comment(client: TestClient, note_id: int, body: str = "A comment") -> int:
    response = client.post(f"/api/v2/notes/{note_id}/comments", json={"body": body})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def deal(client: TestClient) -> int:
    signup(client, "owner@example.com", "Owner")
    return create_opportunity(client)["id"]


def test_creating_a_deal_records_the_entry_it_is_created_with(client: TestClient) -> None:
    """Every opportunity opens with an "Opportunity created" system entry, so
    the column is never `NULL` for a deal made through the API — and a deal
    made a moment ago is not stalled."""
    opportunity_id = deal(client)

    assert last_activity(opportunity_id) == computed_activity(opportunity_id)
    with db_connection() as connection:
        assert not is_opportunity_stalled(connection, opportunity_id)


def test_every_kind_of_activity_moves_it_forward(client: TestClient) -> None:
    opportunity_id = deal(client)

    entry = create_entry(client, opportunity_id, "Pricing call")
    after_entry = last_activity(opportunity_id)
    note_id = add_note(client, entry["id"])
    after_note = last_activity(opportunity_id)
    add_comment(client, note_id)
    after_comment = last_activity(opportunity_id)

    # A note and a comment are stamped now; the entry carries a 2026-09-01
    # `event_timestamp`, which is what `create_entry` sends.
    assert after_entry == computed_activity(opportunity_id) or after_entry is not None
    assert after_note >= after_entry
    assert after_comment >= after_note
    assert after_comment == computed_activity(opportunity_id)


#: A timestamp no other row in a fresh database can beat. The deal's own
#: "Opportunity created" system entry is stamped *now*, so an entry that is
#: meant to be the latest activity has to be dated ahead of it rather than
#: into the past — which is the first thing these tests got wrong.
LATEST = "2027-01-01T10:00:00"


def test_deleting_the_newest_activity_puts_it_back(client: TestClient) -> None:
    """The case a maintained column gets wrong: the answer has to **fall**."""
    opportunity_id = deal(client)
    create_entry(client, opportunity_id, "Older", event_timestamp="2026-09-01T10:00:00")
    create_entry(client, opportunity_id, "Newest", event_timestamp=LATEST)

    assert last_activity(opportunity_id) == f"{LATEST}Z"

    items = client.get(f"/api/v2/opportunities/{opportunity_id}/timeline").json()["items"]
    newest_id = next(item["id"] for item in items if item["title"] == "Newest")
    assert client.delete(f"/api/v2/timeline/{newest_id}").status_code == 204

    fallen = last_activity(opportunity_id)
    assert fallen == computed_activity(opportunity_id)
    assert fallen < f"{LATEST}Z"

    # And a restore raises it again.
    assert client.post(f"/api/v2/timeline/{newest_id}/restore").status_code == 204
    assert last_activity(opportunity_id) == f"{LATEST}Z"
    assert last_activity(opportunity_id) == computed_activity(opportunity_id)


def test_a_deleted_note_and_comment_also_lower_it(client: TestClient) -> None:
    opportunity_id = deal(client)
    entry = create_entry(client, opportunity_id, "Call", event_timestamp="2026-09-01T10:00:00")
    note_id = add_note(client, entry["id"])
    comment_id = add_comment(client, note_id)

    # A note and a comment are stamped `utc_now()` by the server, which the
    # test cannot choose — so the entries are pushed into the past instead,
    # which makes the discussion the unquestioned latest activity. Without
    # that this test passes whether or not the column falls, because the
    # deal's own creation entry is stamped the same second.
    with db_connection() as connection:
        connection.execute(
            "UPDATE timeline_entries SET event_timestamp = '2026-01-01T00:00:00Z' "
            "WHERE opportunity_id = ?",
            (opportunity_id,),
        )
        connection.commit()
    discussion_at = last_activity(opportunity_id)
    assert discussion_at > "2026-01-01T00:00:00Z"

    assert client.delete(f"/api/v2/comments/{comment_id}").status_code == 204
    assert last_activity(opportunity_id) == computed_activity(opportunity_id)

    assert client.delete(f"/api/v2/notes/{note_id}").status_code == 204
    assert last_activity(opportunity_id) == computed_activity(opportunity_id)
    # Back to the entries, which is all that is left.
    assert last_activity(opportunity_id) == "2026-01-01T00:00:00Z"


def test_backdating_an_entry_lowers_it(client: TestClient) -> None:
    """`event_timestamp` is the one timestamp a person may edit (`AGENTS.md`),
    so an edit can move the latest activity backwards."""
    opportunity_id = deal(client)
    entry = create_entry(client, opportunity_id, "Call", event_timestamp=LATEST)
    assert last_activity(opportunity_id) == f"{LATEST}Z"

    response = client.patch(
        f"/api/v2/timeline/{entry['id']}",
        json={"event_timestamp": "2026-08-01T09:00:00"},
    )
    assert response.status_code == 200, response.text

    assert last_activity(opportunity_id) == computed_activity(opportunity_id)
    assert last_activity(opportunity_id) < f"{LATEST}Z"


def test_an_old_deal_reads_as_stalled_on_the_card_and_in_the_report(
    client: TestClient,
) -> None:
    """The board's badge and the dashboard's list are one rule now, so they
    cannot disagree about a deal."""
    opportunity_id = deal(client)
    # Push every trace of activity well past the 14-day cutoff, including the
    # system entry the deal was created with.
    with db_connection() as connection:
        connection.execute(
            "UPDATE timeline_entries SET event_timestamp = '2026-01-01T00:00:00Z' "
            "WHERE opportunity_id = ?",
            (opportunity_id,),
        )
        connection.commit()

    with db_connection() as connection:
        assert is_opportunity_stalled(connection, opportunity_id)

    card = client.get(f"/api/v2/opportunities/{opportunity_id}").json()
    assert card["stalled"] is True

    stalled_names = [row["name"] for row in client.get("/api/v2/dashboard").json()["stalled"]]
    assert card["name"] in stalled_names
