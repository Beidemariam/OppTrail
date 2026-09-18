"""Search: the FTS5 index, its triggers, and the endpoint over them.

Milestone 1.4 (`docs/ROADMAP.md` Phase 1, ADR 0007). Three properties carry it:

- the index says what the tables say — through inserts, edits, soft deletes,
  the cascade, and a rebuild;
- a search answers with rows the caller is allowed to read, and with no others;
- the timeline's keyword filter, now asked of the index, still answers what it
  answered before.

The index is maintained by triggers written in SQL, so several tests here look
at `search_index` directly. That is deliberate: a test that only went through
the endpoint could not tell a correct index from a query that happens to
compensate for a wrong one.
"""

import random
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from conftest import CsrfClient
from fastapi.testclient import TestClient
from test_migrations import build_mvp_database

from app.database import db_connection, initialize_database
from app.permissions import ACCESSIBLE_OPPORTUNITY_IDS_SQL
from app.search import (
    SEARCH_DOCUMENTS_SQL,
    build_snippet,
    document_id,
    match_expression,
    rebuild_search_index,
)
from app.settings import settings

PROCUREMENT = "Procurement raised an objection about the addendum"


def signup(client: TestClient, email: str = "owner@example.com", name: str = "Owner") -> dict:
    response = client.post(
        "/api/auth/signup",
        json={"email": email, "password": "password123", "name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()["user"]


def login(client: TestClient, email: str) -> None:
    assert (
        client.post("/api/auth/login", json={"email": email, "password": "password123"}).status_code
        == 200
    )


def create_opportunity(client: TestClient, name: str = "Northwind rollout") -> dict:
    response = client.post(
        "/api/opportunities",
        json={
            "name": name,
            "account_name": "Northwind",
            "value": "25000",
            "currency": "USD",
            "stage": "Prospecting",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_entry(
    client: TestClient,
    opportunity_id: int,
    title: str = "Discovery call",
    body: str = PROCUREMENT,
    entry_type: str = "call",
    event_timestamp: str = "2026-09-01T10:00:00",
) -> dict:
    response = client.post(
        f"/api/opportunities/{opportunity_id}/timeline",
        json={
            "type": entry_type,
            "title": title,
            "body": body,
            "event_timestamp": event_timestamp,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_note(client: TestClient, entry_id: int, body: str) -> dict:
    response = client.post(f"/api/timeline/{entry_id}/notes", json={"body": body})
    assert response.status_code == 201, response.text
    return response.json()


def create_comment(client: TestClient, note_id: int, body: str) -> dict:
    response = client.post(f"/api/notes/{note_id}/comments", json={"body": body})
    assert response.status_code == 201, response.text
    return response.json()


def share(client: TestClient, opportunity_id: int, email: str, role: str) -> None:
    response = client.post(
        f"/api/opportunities/{opportunity_id}/shares",
        json={"email": email, "role": role},
    )
    assert response.status_code == 201, response.text


def search(client: TestClient, query: str, **params: object) -> dict:
    suffix = "".join(f"&{key}={value}" for key, value in params.items())
    response = client.get(f"/api/v2/search?q={query}{suffix}")
    assert response.status_code == 200, response.text
    return response.json()


def kinds_and_ids(page: dict) -> list[tuple[str, int]]:
    return [(item["kind"], item["id"]) for item in page["items"]]


def indexed_document_ids(query: str = '"procur"*') -> list[int]:
    """The rowids the index itself matches, without going through a route."""
    with db_connection() as connection:
        rows = connection.execute(
            "SELECT rowid FROM search_index WHERE search_index MATCH ?",
            (query,),
        ).fetchall()
    return sorted(row["rowid"] for row in rows)


# --- the index ------------------------------------------------------------


def test_writes_are_indexed_under_the_documented_rowid(client: TestClient) -> None:
    """The rowid encoding in `app/search.py` is the one the triggers use.

    Those two live in different languages and different files — the constants
    here, the arithmetic in revision 0002's SQL — so the agreement is asserted
    rather than assumed.
    """
    signup(client)
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    note = create_note(client, entry["id"], "Legal has questions about procurement")
    comment = create_comment(client, note["id"], "Procurement replied")

    assert indexed_document_ids() == sorted(
        [
            document_id("entry", entry["id"]),
            document_id("note", note["id"]),
            document_id("comment", comment["id"]),
        ]
    )


def test_editing_a_note_replaces_its_indexed_text(client: TestClient) -> None:
    signup(client)
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"], body="Nothing relevant here")
    note = create_note(client, entry["id"], "Original wording about procurement")

    assert (
        client.patch(
            f"/api/notes/{note['id']}", json={"body": "Rewritten to mention logistics"}
        ).status_code
        == 200
    )

    assert indexed_document_ids() == []
    assert indexed_document_ids('"logistics"*') == [document_id("note", note["id"])]


def test_soft_deleting_a_note_removes_it_from_the_index_and_from_results(
    client: TestClient,
) -> None:
    """The acceptance line: "deleting a note removes it from results"."""
    signup(client)
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"], body="Nothing relevant here")
    note = create_note(client, entry["id"], "Legal has questions about procurement")

    assert kinds_and_ids(search(client, "procurement")) == [("note", note["id"])]

    assert client.delete(f"/api/notes/{note['id']}").status_code == 204

    assert indexed_document_ids() == []
    assert search(client, "procurement")["items"] == []


def test_the_soft_delete_cascade_empties_the_index_for_the_whole_tree(
    client: TestClient,
) -> None:
    """Deleting the opportunity takes its entries, notes and comments with it
    (`app/soft_delete.py`), and every level's trigger has to fire for the index
    to agree with what the timeline now shows."""
    signup(client)
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    note = create_note(client, entry["id"], "Procurement follow-up")
    create_comment(client, note["id"], "Procurement confirmed")

    assert len(indexed_document_ids()) == 3

    assert client.delete(f"/api/opportunities/{opportunity['id']}").status_code == 204

    assert indexed_document_ids() == []
    assert search(client, "procurement")["items"] == []


def test_a_restored_row_is_indexed_again(client: TestClient) -> None:
    """Nothing in the application undeletes a row, but the trigger's two halves
    are one statement each and the restoring half would otherwise never run.
    `deleted_at` is cleared here directly, which is the only way in."""
    signup(client)
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"], body="Nothing relevant here")
    note = create_note(client, entry["id"], "Procurement follow-up")
    assert client.delete(f"/api/notes/{note['id']}").status_code == 204
    assert indexed_document_ids() == []

    with db_connection() as connection:
        connection.execute("UPDATE notes SET deleted_at = NULL WHERE id = ?", (note["id"],))
        connection.commit()

    assert indexed_document_ids() == [document_id("note", note["id"])]


def test_a_hard_delete_removes_the_index_row(client: TestClient) -> None:
    """No application path hard-deletes user data (`tests/test_soft_delete.py`
    fails the build over it), but the index must not survive a row removed by
    any other means — a purge script, a future migration."""
    signup(client)
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    create_note(client, entry["id"], "Procurement follow-up")

    with db_connection() as connection:
        connection.execute(
            "DELETE FROM note_versions WHERE note_id IN (SELECT id FROM notes WHERE entry_id = ?)",
            (entry["id"],),
        )
        connection.execute("DELETE FROM notes WHERE entry_id = ?", (entry["id"],))
        connection.execute("DELETE FROM timeline_entries WHERE id = ?", (entry["id"],))
        connection.commit()

    assert indexed_document_ids() == []


def test_updating_an_already_deleted_row_leaves_the_index_alone(client: TestClient) -> None:
    """A soft-deleted row has no index row, so neither half of the update
    trigger may touch one: FTS5's `'delete'` command against a rowid that is
    not there corrupts a contentless index."""
    signup(client)
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"], body="Nothing relevant here")
    note = create_note(client, entry["id"], "Procurement follow-up")
    assert client.delete(f"/api/notes/{note['id']}").status_code == 204

    with db_connection() as connection:
        connection.execute(
            "UPDATE notes SET body = 'Procurement, edited while deleted' WHERE id = ?",
            (note["id"],),
        )
        connection.commit()
        integrity = connection.execute(
            "INSERT INTO search_index(search_index) VALUES ('integrity-check')"
        )
        assert integrity.rowcount is not None

    assert indexed_document_ids() == []


# --- rebuild --------------------------------------------------------------


def test_rebuild_reproduces_the_index_the_migration_built(client: TestClient) -> None:
    """`app/search.py`'s rebuild and revision 0002's backfill are the same three
    statements written twice — the revision cannot import the module, because a
    revision is frozen in time. This is what fails if they drift."""
    signup(client)
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    note = create_note(client, entry["id"], "Procurement follow-up")
    create_comment(client, note["id"], "Procurement confirmed")
    deleted = create_note(client, entry["id"], "Procurement note that goes away")
    assert client.delete(f"/api/notes/{deleted['id']}").status_code == 204

    before = indexed_document_ids()

    with db_connection() as connection:
        indexed = rebuild_search_index(connection)
        connection.commit()

    assert indexed == 4  # two entries (one is "Opportunity created"), a note, a comment
    assert indexed_document_ids() == before
    assert document_id("note", deleted["id"]) not in before


def test_rebuild_restores_an_emptied_index(client: TestClient) -> None:
    signup(client)
    opportunity = create_opportunity(client)
    create_entry(client, opportunity["id"])

    with db_connection() as connection:
        connection.execute("INSERT INTO search_index(search_index) VALUES ('delete-all')")
        connection.commit()
    assert search(client, "procurement")["items"] == []

    with db_connection() as connection:
        rebuild_search_index(connection)
        connection.commit()

    assert kinds_and_ids(search(client, "procurement")) == [("entry", 2)]


# --- the endpoint ---------------------------------------------------------


def test_results_are_ranked_and_snippeted(client: TestClient) -> None:
    signup(client)
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"], body="A" * 400 + " procurement " + "B" * 400)
    note = create_note(client, entry["id"], "Procurement")

    page = search(client, "procurement")

    # bm25 ranks the short note above the long entry: the same one match
    # carries more of the document.
    assert kinds_and_ids(page) == [("note", note["id"]), ("entry", entry["id"])]

    note_result, entry_result = page["items"]
    assert note_result["snippet"] == {
        "text": "Procurement",
        "matches": [{"start": 0, "length": 11}],
    }
    assert note_result["opportunity_name"] == "Northwind rollout"
    assert note_result["entry_id"] == entry["id"]
    assert note_result["note_id"] == note["id"]
    assert note_result["author_name"] == "Owner"

    # The long entry's excerpt is a window around the match, not its head.
    snippet = entry_result["snippet"]
    assert snippet["text"].startswith("…AAA")
    assert snippet["text"].endswith("BBB…")
    assert len(snippet["matches"]) == 1
    match = snippet["matches"][0]
    assert snippet["text"][match["start"] : match["start"] + match["length"]] == "procurement"
    assert entry_result["title"] == "Discovery call"


def test_search_finds_entries_notes_and_comments_across_opportunities(
    client: TestClient,
) -> None:
    signup(client)
    first = create_opportunity(client, "Northwind rollout")
    second = create_opportunity(client, "Globex renewal")
    first_entry = create_entry(client, first["id"], title="Procurement call")
    second_entry = create_entry(client, second["id"], body="Nothing relevant here")
    note = create_note(client, second_entry["id"], "Procurement asked for the addendum")
    comment = create_comment(client, note["id"], "Procurement signed it off")

    page = search(client, "procurement")

    assert sorted(kinds_and_ids(page)) == sorted(
        [("entry", first_entry["id"]), ("note", note["id"]), ("comment", comment["id"])]
    )
    assert {item["opportunity_name"] for item in page["items"]} == {
        "Northwind rollout",
        "Globex renewal",
    }


def test_search_is_scoped_to_what_the_caller_can_read(client: TestClient) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    viewer = signup(client, "viewer@example.com", "Viewer")
    stranger = signup(client, "stranger@example.com", "Stranger")
    assert owner["id"] != viewer["id"] != stranger["id"]

    login(client, "owner@example.com")
    shared = create_opportunity(client, "Shared deal")
    private = create_opportunity(client, "Private deal")
    shared_entry = create_entry(client, shared["id"], title="Procurement call")
    create_entry(client, private["id"], title="Procurement call")
    share(client, shared["id"], "viewer@example.com", "viewer")

    login(client, "viewer@example.com")
    assert kinds_and_ids(search(client, "procurement")) == [("entry", shared_entry["id"])]

    login(client, "stranger@example.com")
    assert search(client, "procurement")["items"] == []

    # And a share that is taken away takes its rows with it.
    login(client, "owner@example.com")
    assert (
        client.delete(f"/api/opportunities/{shared['id']}/shares/{viewer['id']}").status_code == 204
    )
    login(client, "viewer@example.com")
    assert search(client, "procurement")["items"] == []


def test_search_filters_by_type_author_and_date(client: TestClient) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    editor = signup(client, "editor@example.com", "Editor")

    login(client, "owner@example.com")
    opportunity = create_opportunity(client)
    call = create_entry(
        client,
        opportunity["id"],
        title="Procurement call",
        entry_type="call",
        event_timestamp="2026-09-01T10:00:00",
    )
    email = create_entry(
        client,
        opportunity["id"],
        title="Procurement email",
        entry_type="email",
        event_timestamp="2026-09-10T10:00:00",
    )
    share(client, opportunity["id"], "editor@example.com", "editor")

    login(client, "editor@example.com")
    note = create_note(client, call["id"], "Procurement note from the editor")

    login(client, "owner@example.com")
    assert kinds_and_ids(search(client, "procurement", type="email")) == [("entry", email["id"])]
    # The note is on the call, so the call's type selects it too.
    assert sorted(kinds_and_ids(search(client, "procurement", type="call"))) == sorted(
        [("entry", call["id"]), ("note", note["id"])]
    )
    assert kinds_and_ids(search(client, "procurement", author_id=editor["id"])) == [
        ("note", note["id"])
    ]
    assert sorted(kinds_and_ids(search(client, "procurement", author_id=owner["id"]))) == sorted(
        [("entry", call["id"]), ("entry", email["id"])]
    )

    windowed = search(
        client,
        "procurement",
        **{"from": "2026-09-05T00:00:00Z", "to": "2026-09-15T00:00:00Z"},
    )
    assert kinds_and_ids(windowed) == [("entry", email["id"])]


def test_search_pages_walk_every_match_exactly_once(client: TestClient) -> None:
    signup(client)
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"], body="Nothing relevant here")
    for index in range(7):
        create_note(client, entry["id"], f"Procurement note number {index}")

    seen: list[tuple[str, int]] = []
    cursor: str | None = None
    pages = 0
    while True:
        suffix = f"&cursor={cursor}" if cursor else ""
        page = client.get(f"/api/v2/search?q=procurement&limit=2{suffix}").json()
        seen.extend(kinds_and_ids(page))
        pages += 1
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert pages == 4
    assert len(seen) == len(set(seen)) == 7


def test_a_query_with_no_words_matches_nothing(client: TestClient) -> None:
    signup(client)
    opportunity = create_opportunity(client)
    create_entry(client, opportunity["id"])

    assert search(client, "%21%21%21") == {"items": [], "next_cursor": None}


def test_search_requires_a_query(client: TestClient) -> None:
    signup(client)

    response = client.get("/api/v2/search")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "q" in response.json()["error"]["fields"]


def test_a_quote_in_the_query_is_a_word_not_an_operator(client: TestClient) -> None:
    """The user's text never reaches FTS5's query parser (`match_expression`),
    so nothing typed into a search box can be a syntax error or an operator."""
    signup(client)
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])

    # Quotation marks are punctuation between words, not phrase syntax.
    assert kinds_and_ids(search(client, "%22procurement%22")) == [("entry", entry["id"])]
    # "OR" is a word like any other, and words are ANDed: the entry has no word
    # beginning "or", so this matches nothing rather than either term.
    assert search(client, "procurement%20OR%20addendum")["items"] == []
    # And an expression that would be a syntax error is answered, not raised.
    assert search(client, "NEAR%28procurement")["items"] == []


# --- the timeline filter, now asked of the index --------------------------


def test_timeline_keyword_filter_matches_entries_notes_and_comments(
    client: TestClient,
) -> None:
    signup(client)
    opportunity = create_opportunity(client)
    create_entry(client, opportunity["id"], title="Kickoff", body=PROCUREMENT)
    by_note = create_entry(client, opportunity["id"], title="Demo", body="Nothing here")
    note = create_note(client, by_note["id"], "Procurement asked for the addendum")
    by_comment = create_entry(client, opportunity["id"], title="Review", body="Nothing here")
    other_note = create_note(client, by_comment["id"], "Nothing here either")
    create_comment(client, other_note["id"], "Procurement signed it off")
    create_entry(client, opportunity["id"], title="Unrelated", body="Nothing here")
    assert note["entry_id"] == by_note["id"]

    filtered = client.get(f"/api/opportunities/{opportunity['id']}/timeline?q=procurement")

    assert sorted(entry["title"] for entry in filtered.json()["entries"]) == [
        "Demo",
        "Kickoff",
        "Review",
    ]


def test_timeline_keyword_filter_matches_word_prefixes(client: TestClient) -> None:
    """`LIKE '%proc%'` matched inside words; the index matches word prefixes.
    A partial word typed into the filter box still has to find the entry."""
    signup(client)
    opportunity = create_opportunity(client)
    create_entry(client, opportunity["id"], title="Kickoff", body=PROCUREMENT)

    filtered = client.get(f"/api/opportunities/{opportunity['id']}/timeline?q=proc")

    assert [entry["title"] for entry in filtered.json()["entries"]] == ["Kickoff"]


def test_timeline_keyword_filter_drops_deleted_notes(client: TestClient) -> None:
    signup(client)
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"], title="Demo", body="Nothing here")
    note = create_note(client, entry["id"], "Procurement asked for the addendum")
    assert client.delete(f"/api/notes/{note['id']}").status_code == 204

    filtered = client.get(f"/api/opportunities/{opportunity['id']}/timeline?q=procurement")

    assert filtered.json()["entries"] == []


def test_timeline_keyword_filter_ignores_other_opportunities(client: TestClient) -> None:
    """The index is global; the filter is not."""
    signup(client)
    first = create_opportunity(client, "Northwind rollout")
    second = create_opportunity(client, "Globex renewal")
    create_entry(client, first["id"], title="Kickoff", body=PROCUREMENT)
    create_entry(client, second["id"], title="Other kickoff", body=PROCUREMENT)

    filtered = client.get(f"/api/opportunities/{first['id']}/timeline?q=procurement")

    assert [entry["title"] for entry in filtered.json()["entries"]] == ["Kickoff"]


def test_timeline_keyword_filter_with_no_words_matches_nothing(client: TestClient) -> None:
    signup(client)
    opportunity = create_opportunity(client)
    create_entry(client, opportunity["id"])

    filtered = client.get(f"/api/opportunities/{opportunity['id']}/timeline?q=%21%21%21")

    assert filtered.json()["entries"] == []


# --- the reason for the index ---------------------------------------------


def query_plan(sql: str, params: tuple[object, ...]) -> list[str]:
    with db_connection() as connection:
        return [row["detail"] for row in connection.execute(f"EXPLAIN QUERY PLAN {sql}", params)]


def test_search_reads_the_index_and_never_scans_a_source_table(client: TestClient) -> None:
    """ADR 0007's whole argument is the shape of the plan, not a stopwatch.

    The `LIKE` filter this replaced had to read every entry, note and comment
    to answer; the index is only worth having if this one does not. The plan is
    asserted rather than the wall clock because the plan is what stops being
    true when someone adds a predicate FTS5 cannot drive.
    """
    signup(client)
    opportunity = create_opportunity(client)
    create_entry(client, opportunity["id"])

    sql = (
        f"{SEARCH_DOCUMENTS_SQL} "
        f"WHERE documents.opportunity_id IN ({ACCESSIBLE_OPPORTUNITY_IDS_SQL}) "
        "ORDER BY documents.rank ASC, documents.document_id ASC LIMIT ?"
    )
    plan = query_plan(sql, ('"procurement"*', 1, 1, 51))

    # The index drives the query: three MATCH scans, one per document kind.
    assert sum("search_index VIRTUAL TABLE" in step for step in plan) == 3
    # And every match is resolved by rowid, so no source table is read whole.
    for table in ("timeline_entries", "notes", "comments"):
        assert f"SCAN {table}" not in plan
        assert any(step.startswith(f"SEARCH {table} USING INTEGER PRIMARY KEY") for step in plan), (
            f"{table} is not reached by rowid: {plan}"
        )


# The corpus the latency assertion below runs against. Not `AGENTS.md`'s
# confirmed 800k-row scale -- building that per test run costs more than the
# whole suite -- and milestone R.3 owns the measurement at full size against
# R.7's large seed. What this size is enough for is the property that decides
# the budget: a rare term costs what the posting list costs, not what the
# corpus costs, so the figure here barely moves as the corpus grows.
BENCHMARK_ENTRIES = 8_000
BENCHMARK_WORDS = (
    "renewal",
    "pricing",
    "addendum",
    "logistics",
    "procurement",
    "discount",
    "pilot",
    "redlines",
    "kickoff",
    "handover",
)
RARE_TERM = "zarquon"
SEARCH_BUDGET_SECONDS = 0.3


def build_corpus(opportunity_id: int, user_id: int) -> int:
    """One entry, note and comment each for `BENCHMARK_ENTRIES`, written
    straight to SQLite: the triggers index them exactly as a route would, and
    going through HTTP for 24,000 rows would time out the suite, not the API.

    Returns the id of the one entry carrying the rare term.
    """
    filler = random.Random(7)
    stamp = "2026-01-04T09:00:00Z"
    with db_connection() as connection:
        # Above whatever the opportunity's own "created" entry took.
        first = int(connection.execute("SELECT MAX(id) FROM timeline_entries").fetchone()[0]) + 1

    entries, notes, comments = [], [], []
    for index in range(first, first + BENCHMARK_ENTRIES):
        body = " ".join(filler.choices(BENCHMARK_WORDS, k=20))
        entries.append((index, opportunity_id, user_id, "call", f"Entry {index}", body, stamp))
        notes.append((index, index, user_id, body, stamp))
        comments.append((index, index, user_id, body, stamp))
    # The needle: one document in the corpus carries the rare term.
    entries[-1] = entries[-1][:5] + (f"{entries[-1][5]} {RARE_TERM}",) + entries[-1][6:]

    with db_connection() as connection:
        connection.executemany(
            "INSERT INTO timeline_entries"
            " (id, opportunity_id, created_by, type, title, body, event_timestamp, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [row + (stamp,) for row in entries],
        )
        connection.executemany(
            "INSERT INTO notes (id, entry_id, created_by, body, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [row + (stamp,) for row in notes],
        )
        connection.executemany(
            "INSERT INTO comments (id, note_id, created_by, body, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            comments,
        )
        connection.commit()
    return int(entries[-1][0])


def test_a_rare_term_is_ranked_and_snippeted_inside_the_budget(client: TestClient) -> None:
    """Phase 1's acceptance line: a rare term returns ranked, snippeted results
    in under 300 ms. The `LIKE` filter this replaced took 294 ms against that
    same budget at full scale (ADR 0007) *because* the term was rare -- it had
    to read everything to prove there was nothing else.

    This is the acceptance line's own assertion, not a scan detector: at this
    corpus size SQLite can still answer a scan-shaped query inside the budget,
    which is what `test_search_reads_the_index_and_never_scans_a_source_table`
    above is for. The two are separate on purpose -- one pins the number the
    roadmap asks for, the other pins the reason it stays true as the corpus
    grows.
    """
    user = signup(client)
    opportunity = create_opportunity(client)
    needle = build_corpus(opportunity["id"], user["id"])

    started = time.perf_counter()
    page = search(client, RARE_TERM)
    elapsed = time.perf_counter() - started

    assert elapsed < SEARCH_BUDGET_SECONDS, f"{elapsed:.3f}s for a rare term"
    assert kinds_and_ids(page) == [("entry", needle)]
    snippet = page["items"][0]["snippet"]
    assert snippet["matches"], "the matched word is not marked in the excerpt"
    start, length = snippet["matches"][0]["start"], snippet["matches"][0]["length"]
    assert snippet["text"][start : start + length].lower() == RARE_TERM


# --- units ----------------------------------------------------------------


def test_match_expression_builds_prefix_terms() -> None:
    assert match_expression("procurement addendum") == '"procurement"* "addendum"*'
    assert match_expression('  "quoted" OR x  ') == '"quoted"* "OR"* "x"*'
    assert match_expression("!!!") is None


def test_build_snippet_marks_every_match_in_the_excerpt() -> None:
    snippet = build_snippet("Procurement and more procurement", ["procurement"])

    assert snippet.text == "Procurement and more procurement"
    assert [(match.start, match.length) for match in snippet.matches] == [(0, 11), (21, 11)]


def test_build_snippet_with_no_tokens_marks_nothing() -> None:
    """The empty-token guard in `matches_pattern`. Without it the alternation
    would be empty and the pattern would match at every position, so an
    excerpt would come back highlighted end to end."""
    snippet = build_snippet("Procurement raised an objection", [])

    assert snippet.text == "Procurement raised an objection"
    assert snippet.matches == []


def test_build_snippet_falls_back_to_the_head_of_the_text() -> None:
    """Stemming can match a row this literal pass cannot highlight. The result
    still carries an excerpt rather than being dropped."""
    snippet = build_snippet("Objection raised", ["objections"])

    assert snippet.text == "Objection raised"
    assert snippet.matches == []


# --- a legacy database ----------------------------------------------------


@pytest.fixture
def legacy_database_url(tmp_path: Path) -> Iterator[str]:
    original = settings.database_url
    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    settings.database_url = url
    try:
        yield url
    finally:
        settings.database_url = original


def test_upgrading_an_mvp_database_indexes_the_rows_it_already_has(
    legacy_database_url: str,
) -> None:
    """Revision 0002's backfill, on the database that actually needs it: a
    pre-Alembic installation whose entries, notes and comments were written
    long before the index existed."""
    build_mvp_database(legacy_database_url)

    initialize_database()

    from app.main import app

    with CsrfClient(app) as client:
        login_response = client.post(
            "/api/auth/signup",
            json={"email": "new@example.com", "password": "password123", "name": "New"},
        )
        assert login_response.status_code == 201
        # The legacy owner's rows are not this user's to read...
        assert search(client, "budget")["items"] == []

    assert indexed_document_ids('"budget"*') == [document_id("entry", 1)]
    assert indexed_document_ids('"agreed"*') == [document_id("comment", 1)]
