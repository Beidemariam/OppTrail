"""A sealed entry: absent, and absent without trace (milestone R.1b, R.1c).

The human's ask: *"the ability to keep entries private since as an owner, I
might not want to share everything with whoever I give read or edit rights to
the opportunity."*

R.1b built the sealed shape -- the row stayed in everybody's timeline, emptied
of everything but its author and its time -- and the human overruled it at the
shakedown (**D-209**): *"it is better not to mention anything instead of
saying it is kept private, so the other person doesn't know anything about
what's kept away from them."* So a sealed entry is now simply not in anybody
else's timeline, and `test_a_sealed_entry_is_numbered_per_reader` is the other
half of that: a row that vanished while the numbering stayed would leave a gap
between #1 and #3, which says what the removed card used to say out loud.

The actor this file exists for is the one the authorization matrix cannot
express: somebody who may read the *deal* and may not read one *entry* on it.
"""

from fastapi.testclient import TestClient

from app import ai_service
from app.database import db_connection
from app.export_service import fetch_export_data


def signup(client: TestClient, email: str, name: str) -> dict:
    response = client.post(
        "/api/v2/auth/signup",
        json={"email": email, "password": "password123", "name": name},
    )
    assert response.status_code == 201
    return response.json()["user"]


def login(client: TestClient, email: str) -> None:
    assert (
        client.post(
            "/api/v2/auth/login",
            json={"email": email, "password": "password123"},
        ).status_code
        == 200
    )


def create_opportunity(client: TestClient) -> dict:
    response = client.post(
        "/api/v2/opportunities",
        json={
            "name": "Expansion",
            "account_name": "Acme",
            "value": "25000",
            "currency": "USD",
            "stage": "Prospecting",
            "expected_close_date": "2026-10-15",
        },
    )
    assert response.status_code == 201
    return response.json()


def add_entry(
    client: TestClient,
    opportunity_id: int,
    title: str,
    visibility: str,
    event_timestamp: str = "2026-09-01T10:00:00",
) -> dict:
    response = client.post(
        f"/api/v2/opportunities/{opportunity_id}/timeline",
        json={
            "type": "call",
            "title": title,
            "body": f"The body of {title}",
            "event_timestamp": event_timestamp,
            "visibility": visibility,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def timeline(client: TestClient, opportunity_id: int) -> list[dict]:
    response = client.get(f"/api/v2/opportunities/{opportunity_id}/timeline")
    assert response.status_code == 200
    return response.json()["items"]


def shared_deal(client: TestClient) -> tuple[dict, dict, dict]:
    """One deal, its owner, and an editor it is shared with."""
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    client.post("/api/v2/auth/logout")

    colleague = signup(client, "colleague@example.com", "Colleague")
    client.post("/api/v2/auth/logout")

    login(client, "owner@example.com")
    assert (
        client.post(
            f"/api/v2/opportunities/{opportunity['id']}/shares",
            json={"email": "colleague@example.com", "role": "editor"},
        ).status_code
        == 201
    )
    return owner, colleague, opportunity


def test_a_colleague_meets_no_trace_of_a_sealed_entry(client: TestClient) -> None:
    """R.1c, **D-209**. Not an emptied card: no card.

    The whole of what a colleague could learn from the R.1b shape -- that
    somebody wrote something here, and when -- is what this asserts is gone.
    """
    _, _, opportunity = shared_deal(client)
    shared = add_entry(client, opportunity["id"], "Said out loud", "shared")
    sealed = add_entry(client, opportunity["id"], "Kept back", "private", "2026-09-02T10:00:00")

    client.post("/api/v2/auth/logout")
    login(client, "colleague@example.com")
    entries = {entry["id"]: entry for entry in timeline(client, opportunity["id"])}

    assert sealed["id"] not in entries
    # Not its id, not its author, not its time, in any row of the page.
    assert "2026-09-02T10:00:00Z" not in [entry["event_timestamp"] for entry in entries.values()]
    # And the entry beside it is untouched.
    assert entries[shared["id"]]["title"] == "Said out loud"


def test_its_author_reads_it_whole(client: TestClient) -> None:
    _, _, opportunity = shared_deal(client)
    sealed = add_entry(client, opportunity["id"], "Kept back", "private")

    entries = {entry["id"]: entry for entry in timeline(client, opportunity["id"])}

    assert entries[sealed["id"]]["title"] == "Kept back"
    assert entries[sealed["id"]]["body"] == "The body of Kept back"
    assert entries[sealed["id"]]["visibility"] == "private"


def test_a_sealed_entry_is_numbered_per_reader(client: TestClient) -> None:
    """R.1c, **D-209**: a removed row takes its number with it.

    `ENTRY_SEQUENCE_SQL` counts the entries *this reader* may read. Leaving it
    counting the deal's would leave the colleague reading #1 then #3, which is
    the announcement the card used to make. The cost is that the two people
    call one entry by two numbers -- tolerable precisely because D-139 says
    this number is a reading aid and never an identity, and because a single
    reader's card and the AI's citation still come from this one expression.
    """
    _, _, opportunity = shared_deal(client)
    add_entry(client, opportunity["id"], "First", "shared", "2026-09-01T10:00:00")
    add_entry(client, opportunity["id"], "Second", "private", "2026-09-02T10:00:00")
    add_entry(client, opportunity["id"], "Third", "shared", "2026-09-03T10:00:00")

    owner_numbers = {
        entry["title"]: entry["sequence"] for entry in timeline(client, opportunity["id"])
    }

    client.post("/api/v2/auth/logout")
    login(client, "colleague@example.com")
    colleague_view = timeline(client, opportunity["id"])

    # The three above are backdated to September, so the deal's own system
    # entries -- created, shared -- are stamped now and sort after them.
    assert owner_numbers["Second"] == 2
    assert owner_numbers["Third"] == 3
    # No sealed row, and no gap where it was: the colleague's "Third" is #2.
    assert all(entry["visibility"] == "shared" for entry in colleague_view)
    numbers = sorted(entry["sequence"] for entry in colleague_view)
    assert numbers == list(range(1, len(numbers) + 1))
    third = next(entry for entry in colleague_view if entry["title"] == "Third")
    assert third["sequence"] == 2


def test_a_colleague_cannot_act_on_a_sealed_entry(client: TestClient) -> None:
    """Resolving the parent is where this is enforced, so every write answers
    404 rather than each route remembering to ask."""
    _, _, opportunity = shared_deal(client)
    sealed = add_entry(client, opportunity["id"], "Kept back", "private")

    client.post("/api/v2/auth/logout")
    login(client, "colleague@example.com")

    entry_id = sealed["id"]
    assert (
        client.patch(f"/api/v2/timeline/{entry_id}", json={"title": "Mine now"}).status_code == 404
    )
    assert client.delete(f"/api/v2/timeline/{entry_id}").status_code == 404
    assert (
        client.post(f"/api/v2/timeline/{entry_id}/notes", json={"body": "Reading over"}).status_code
        == 404
    )
    assert client.get(f"/api/v2/timeline/{entry_id}/versions").status_code == 404


def test_only_its_author_may_seal_or_unseal(client: TestClient) -> None:
    """The one field where author-or-owner (D-005) would be wrong: an owner who
    can unseal a colleague's entry is an owner who can read it."""
    _, _, opportunity = shared_deal(client)
    client.post("/api/v2/auth/logout")
    login(client, "colleague@example.com")
    theirs = add_entry(client, opportunity["id"], "The editor's own", "shared")

    client.post("/api/v2/auth/logout")
    login(client, "owner@example.com")
    refused = client.patch(
        f"/api/v2/timeline/{theirs['id']}",
        json={"visibility": "private"},
    )

    assert refused.status_code == 403
    assert "author" in refused.json()["error"]["message"]


def test_sealing_afterwards_withdraws_what_the_entry_told_people(client: TestClient) -> None:
    """The human's ruling: *"even when sealed after the fact, withdraw any
    notification related to it."* A notification is a copy, written at the time
    and read without re-checking the deal, so nothing a later query does can
    unsay it."""
    _, _, opportunity = shared_deal(client)
    entry = add_entry(client, opportunity["id"], "Said out loud", "shared")

    client.post("/api/v2/auth/logout")
    login(client, "colleague@example.com")
    before = client.get("/api/v2/notifications").json()["items"]
    assert any(item["payload"].get("title") == "Said out loud" for item in before)

    client.post("/api/v2/auth/logout")
    login(client, "owner@example.com")
    assert (
        client.patch(
            f"/api/v2/timeline/{entry['id']}",
            json={"visibility": "private"},
        ).status_code
        == 200
    )

    client.post("/api/v2/auth/logout")
    login(client, "colleague@example.com")
    after = client.get("/api/v2/notifications").json()["items"]
    assert not any(item["payload"].get("title") == "Said out loud" for item in after)


def test_unsealing_gives_the_entry_back_without_announcing_it_again(client: TestClient) -> None:
    _, _, opportunity = shared_deal(client)
    entry = add_entry(client, opportunity["id"], "Said out loud", "shared")
    client.patch(f"/api/v2/timeline/{entry['id']}", json={"visibility": "private"})
    client.patch(f"/api/v2/timeline/{entry['id']}", json={"visibility": "shared"})

    client.post("/api/v2/auth/logout")
    login(client, "colleague@example.com")
    entries = {item["id"]: item for item in timeline(client, opportunity["id"])}
    notifications = client.get("/api/v2/notifications").json()["items"]

    # Readable again...
    assert entries[entry["id"]]["title"] == "Said out loud"
    # ...and not news a second time: the withdrawn notification stays withdrawn.
    assert not any(item["payload"].get("title") == "Said out loud" for item in notifications)


def test_a_private_entry_tells_nobody_when_it_is_written(client: TestClient) -> None:
    _, _, opportunity = shared_deal(client)
    add_entry(client, opportunity["id"], "Kept back", "private")

    client.post("/api/v2/auth/logout")
    login(client, "colleague@example.com")
    notifications = client.get("/api/v2/notifications").json()["items"]

    assert not any(item["payload"].get("title") == "Kept back" for item in notifications)


def test_search_does_not_surface_a_sealed_entry_to_anybody_else(client: TestClient) -> None:
    _, _, opportunity = shared_deal(client)
    add_entry(client, opportunity["id"], "Procurement objection", "private")

    found_by_author = client.get("/api/v2/search", params={"q": "procurement"}).json()["items"]
    client.post("/api/v2/auth/logout")
    login(client, "colleague@example.com")
    found_by_colleague = client.get("/api/v2/search", params={"q": "procurement"}).json()["items"]

    assert [item["title"] for item in found_by_author] == ["Procurement objection"]
    assert found_by_colleague == []


def test_the_export_is_per_reader(client: TestClient) -> None:
    owner, colleague, opportunity = shared_deal(client)
    add_entry(client, opportunity["id"], "Said out loud", "shared")
    add_entry(client, opportunity["id"], "Kept back", "private", "2026-09-02T10:00:00")

    with db_connection() as connection:
        for_owner = fetch_export_data(connection, opportunity["id"], owner["id"])
        for_colleague = fetch_export_data(connection, opportunity["id"], colleague["id"])

    assert "Kept back" in [entry["title"] for entry in for_owner["entries"]]
    assert "Kept back" not in [entry["title"] for entry in for_colleague["entries"]]
    assert "Said out loud" in [entry["title"] for entry in for_colleague["entries"]]


def test_invariant_a_sealed_entry_is_not_in_anybody_elses_ai_context(client: TestClient) -> None:
    """The one place a leak would be invisible: a model does not say where its
    information came from, so this is asserted on the context itself rather
    than on an answer."""
    owner, colleague, opportunity = shared_deal(client)
    add_entry(client, opportunity["id"], "Kept back", "private")

    with db_connection() as connection:
        for_author, _ = ai_service.build_timeline_context(
            connection, opportunity["id"], owner["id"]
        )
        for_colleague, _ = ai_service.build_timeline_context(
            connection, opportunity["id"], colleague["id"]
        )

    assert "Kept back" in for_author
    assert "The body of Kept back" in for_author
    assert "Kept back" not in for_colleague
    assert "The body of Kept back" not in for_colleague


def test_a_task_made_from_a_sealed_entry_withholds_where_it_came_from(
    client: TestClient,
) -> None:
    """A task carries its entry's title to whoever it is assigned to, including
    on My Tasks, which spans deals (the human's second ruling).

    **The id goes with the title** (R.1c, **D-209**). R.1b kept `entry_id` and
    let the link 404, which was consistent while the sealed entry still stood
    on the timeline as an empty card. With the card gone, that id is the one
    remaining place a colleague could learn the entry exists.
    """
    _, _, opportunity = shared_deal(client)
    sealed = add_entry(client, opportunity["id"], "Kept back", "private")
    created = client.post(
        f"/api/v2/opportunities/{opportunity['id']}/tasks",
        json={
            "title": "Chase it",
            "entry_id": sealed["id"],
            "assignee_emails": ["colleague@example.com"],
        },
    )
    assert created.status_code == 201
    assert created.json()["entry_title"] == "Kept back"

    client.post("/api/v2/auth/logout")
    login(client, "colleague@example.com")
    mine = client.get("/api/v2/tasks").json()["items"]

    assert [task["title"] for task in mine] == ["Chase it"]
    assert mine[0]["entry_title"] is None
    assert mine[0]["entry_id"] is None


def test_a_file_on_a_sealed_entry_is_not_downloadable_by_anybody_else(client: TestClient) -> None:
    _, _, opportunity = shared_deal(client)
    sealed = add_entry(client, opportunity["id"], "Kept back", "private")
    uploaded = client.post(
        f"/api/v2/timeline/{sealed['id']}/attachments",
        files={"file": ("terms.pdf", b"%PDF-1.4 sealed", "application/pdf")},
    )
    assert uploaded.status_code == 201
    attachment_id = uploaded.json()["id"]

    assert client.get(f"/api/v2/attachments/{attachment_id}/download").status_code == 200

    client.post("/api/v2/auth/logout")
    login(client, "colleague@example.com")

    assert client.get(f"/api/v2/attachments/{attachment_id}/download").status_code == 404


def test_an_existing_timeline_is_untouched_by_the_new_default(client: TestClient) -> None:
    """Revision 0021 backfills `shared`: nothing written before this feature
    existed was authored with privacy in mind, and hiding history people have
    already read would be the wrong kind of surprise."""
    _, _, opportunity = shared_deal(client)

    with db_connection() as connection:
        rows = connection.execute(
            "SELECT visibility FROM timeline_entries WHERE opportunity_id = ?",
            (opportunity["id"],),
        ).fetchall()

    # The system entries the deal was created with.
    assert rows and {row["visibility"] for row in rows} == {"shared"}


def test_the_activity_log_does_not_announce_a_sealed_entry(client: TestClient) -> None:
    """R.1c, **D-209**. The last place a sealed entry announced itself.

    An owner reads the version half of the activity feed, so an edit to a
    colleague's private entry -- or to a note hanging off one -- used to reach
    them as "Colleague edited an entry, changing the title", with its id. The
    content was never there (the version read and the restore both 404), but
    the existence, the author, the time and the field names were, which is the
    whole of what the ruling says a colleague must not learn.
    """
    owner, _, opportunity = shared_deal(client)
    client.post("/api/v2/auth/logout")
    login(client, "colleague@example.com")

    sealed = add_entry(client, opportunity["id"], "Kept back", "private")
    assert (
        client.patch(f"/api/v2/timeline/{sealed['id']}", json={"title": "Kept back, revised"})
    ).status_code == 200
    note = client.post(
        f"/api/v2/timeline/{sealed['id']}/notes", json={"body": "A private note"}
    ).json()
    assert (
        client.patch(
            f"/api/v2/notes/{note['id']}",
            json={"body": "A private note, revised", "updated_at": note["updated_at"]},
        )
    ).status_code == 200

    # The same two edits on a shared entry, which the owner *should* read.
    shared = add_entry(client, opportunity["id"], "Said out loud", "shared")
    assert (
        client.patch(f"/api/v2/timeline/{shared['id']}", json={"title": "Said out loud, again"})
    ).status_code == 200

    client.post("/api/v2/auth/logout")
    login(client, "owner@example.com")
    response = client.get(f"/api/v2/opportunities/{opportunity['id']}/activity")
    assert response.status_code == 200
    edits = [
        event["detail"]
        for event in response.json()["items"]
        if event["detail"]["source"] == "version"
    ]

    assert {edit["target_id"] for edit in edits if edit["target"] == "timeline_entry"} == {
        shared["id"]
    }
    assert [edit for edit in edits if edit["target"] == "note"] == []
    assert owner["id"]


def test_an_owner_still_reads_their_own_sealed_entrys_edits(client: TestClient) -> None:
    """The predicate is the reader's, not a blanket exclusion: an owner who
    sealed their own entry keeps its history in their own feed."""
    _, _, opportunity = shared_deal(client)
    sealed = add_entry(client, opportunity["id"], "Mine alone", "private")
    assert (
        client.patch(f"/api/v2/timeline/{sealed['id']}", json={"title": "Mine alone, revised"})
    ).status_code == 200

    response = client.get(f"/api/v2/opportunities/{opportunity['id']}/activity")
    targets = {
        event["detail"]["target_id"]
        for event in response.json()["items"]
        if event["detail"]["source"] == "version" and event["detail"]["target"] == "timeline_entry"
    }
    assert sealed["id"] in targets
