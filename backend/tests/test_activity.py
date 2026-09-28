"""One activity log per opportunity (milestone 3.0, D-101).

Three mechanisms record what happens to an opportunity -- system timeline
entries, audit log rows and version rows -- and `GET .../activity` is the one
chronological read over all three. What this suite holds is the four rules
that make the merge trustworthy: every event appears exactly once, a row keeps
the visibility of the source it came from, the cursor walks the merged order
rather than any one table's, and an edit to something since deleted is not
reported as if it were still there.

The authorization matrix owns the per-actor status codes; what is checked here
is which rows each actor is given.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_timeline import edit_note

from app.activity import ACTIVITY_STRIDE, SOURCE_RANKS


def signup(client: TestClient, email: str, name: str) -> int:
    response = client.post(
        "/api/v2/auth/signup",
        json={"email": email, "password": "password123", "name": name},
    )
    assert response.status_code == 201, response.text
    user_id: int = response.json()["user"]["id"]
    return user_id


def login(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/v2/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 200, response.text


def create_opportunity(client: TestClient, name: str = "Acme Expansion") -> dict[str, Any]:
    response = client.post(
        "/api/v2/opportunities",
        json={
            "name": name,
            "account_name": "Acme",
            "value": "185000",
            "currency": "USD",
            "stage": "Qualification",
            "expected_close_date": "2026-12-01",
        },
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def create_entry(client: TestClient, opportunity_id: int, title: str = "Discovery call") -> int:
    response = client.post(
        f"/api/v2/opportunities/{opportunity_id}/timeline",
        json={
            "type": "call",
            "title": title,
            "body": "Walked the procurement process.",
            "event_timestamp": "2026-09-04T10:00:00Z",
        },
    )
    assert response.status_code == 201, response.text
    entry_id: int = response.json()["id"]
    return entry_id


def add_note(client: TestClient, entry_id: int, body: str = "First draft") -> int:
    response = client.post(f"/api/v2/timeline/{entry_id}/notes", json={"body": body})
    assert response.status_code == 201, response.text
    note_id: int = response.json()["id"]
    return note_id


def add_comment(client: TestClient, note_id: int, body: str = "Noted") -> int:
    response = client.post(f"/api/v2/notes/{note_id}/comments", json={"body": body})
    assert response.status_code == 201, response.text
    comment_id: int = response.json()["id"]
    return comment_id


def activity(client: TestClient, opportunity_id: int, query: str = "") -> list[dict[str, Any]]:
    response = client.get(f"/api/v2/opportunities/{opportunity_id}/activity{query}")
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


def sources(events: list[dict[str, Any]]) -> list[str]:
    return [event["detail"]["source"] for event in events]


def test_a_new_opportunity_reports_only_its_creation(client: TestClient) -> None:
    """Version 1 is the creation baseline, not an edit (D-097), so the
    opportunity's own creation reaches the feed once -- through the system
    entry that the timeline also shows."""
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)

    events = activity(client, opportunity["id"])

    assert sources(events) == ["system_entry"]
    assert events[0]["detail"]["title"] == "Opportunity created"
    assert events[0]["actor_name"] == "Owner"


def test_an_edit_reports_the_fields_it_moved(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    response = client.patch(
        f"/api/v2/opportunities/{opportunity['id']}",
        json={"name": "Acme Renewal", "value": "210000"},
    )
    assert response.status_code == 200, response.text

    events = activity(client, opportunity["id"])

    assert sources(events) == ["system_entry", "version"]
    edit = events[1]["detail"]
    assert edit["target"] == "opportunity"
    assert edit["target_id"] == opportunity["id"]
    assert edit["version_number"] == 2
    assert edit["changed_fields"] == ["name", "value"]


def test_a_stage_change_is_reported_once_by_its_system_entry(client: TestClient) -> None:
    """The stage `PATCH` writes both a `stage_change` system entry and a
    version row. Only the system entry is an event; the version row that moved
    nothing else would say the same thing twice."""
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    response = client.patch(
        f"/api/v2/opportunities/{opportunity['id']}",
        json={"stage": "Proposal"},
    )
    assert response.status_code == 200, response.text

    events = activity(client, opportunity["id"])

    assert sources(events) == ["system_entry", "system_entry"]
    assert "Proposal" in events[1]["detail"]["body"]


def test_an_edit_that_also_moves_the_stage_is_still_reported(client: TestClient) -> None:
    """Only a stage-*only* edit is silent: the system entry covers the stage,
    and nothing else covers the rest of what that write changed."""
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    response = client.patch(
        f"/api/v2/opportunities/{opportunity['id']}",
        json={"stage": "Proposal", "value": "260000"},
    )
    assert response.status_code == 200, response.text

    events = activity(client, opportunity["id"])

    assert sources(events) == ["system_entry", "system_entry", "version"]
    assert events[2]["detail"]["changed_fields"] == ["value", "stage"]


def test_entry_and_note_edits_are_reported_against_what_they_edited(
    client: TestClient,
) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry_id = create_entry(client, opportunity["id"])
    note_id = add_note(client, entry_id)

    assert (
        client.patch(f"/api/v2/timeline/{entry_id}", json={"title": "Discovery call (2)"})
    ).status_code == 200
    assert (edit_note(client, note_id, "Second draft")).status_code == 200

    events = activity(client, opportunity["id"])
    edits = [event["detail"] for event in events if event["detail"]["source"] == "version"]

    assert [(edit["target"], edit["target_id"], edit["changed_fields"]) for edit in edits] == [
        ("timeline_entry", entry_id, ["title"]),
        ("note", note_id, ["body"]),
    ]


def test_a_deletion_is_reported_from_the_audit_log(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry_id = create_entry(client, opportunity["id"])

    assert client.delete(f"/api/v2/timeline/{entry_id}").status_code == 204

    events = activity(client, opportunity["id"])
    audit = [event for event in events if event["detail"]["source"] == "audit_log"]

    assert [event["detail"]["action"] for event in audit] == ["timeline_entry_deleted"]
    assert audit[0]["detail"]["detail"]["entry_id"] == entry_id
    assert audit[0]["actor_name"] == "Owner"


def test_an_edit_to_something_since_deleted_leaves_the_feed(client: TestClient) -> None:
    """Every read filters `deleted_at IS NULL` at each level it joins through.
    The delete itself stays, as an audit row -- that is the record that the
    note existed and went."""
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry_id = create_entry(client, opportunity["id"])
    note_id = add_note(client, entry_id)
    assert (edit_note(client, note_id, "Second draft")).status_code == 200

    before = activity(client, opportunity["id"])
    assert "version" in sources(before)

    assert client.delete(f"/api/v2/notes/{note_id}").status_code == 204

    after = activity(client, opportunity["id"])
    assert "version" not in sources(after)
    audit = [event for event in after if event["detail"]["source"] == "audit_log"]
    assert [event["detail"]["action"] for event in audit] == ["note_deleted"]

    assert client.post(f"/api/v2/notes/{note_id}/restore").status_code == 204
    assert "version" in sources(activity(client, opportunity["id"]))


def test_sharing_is_reported_once_by_its_system_entry(client: TestClient) -> None:
    """A share writes a system entry and an audit row. The system entry is
    what every reader with access already sees, so the feed keeps that one;
    `GET .../audit-log` still answers with both."""
    signup(client, "owner@example.com", "Owner")
    signup(client, "editor@example.com", "Editor")
    login(client, "owner@example.com")
    opportunity = create_opportunity(client)

    response = client.post(
        f"/api/v2/opportunities/{opportunity['id']}/shares",
        json={"email": "editor@example.com", "role": "editor"},
    )
    assert response.status_code == 201, response.text

    events = activity(client, opportunity["id"])
    assert sources(events) == ["system_entry", "system_entry"]
    assert events[1]["detail"]["title"] == "Shared with Editor"

    audit = client.get(f"/api/v2/opportunities/{opportunity['id']}/audit-log")
    assert [item["action"] for item in audit.json()["items"]] == ["share_added"]


def test_an_ownership_transfer_is_reported_once_by_its_system_entry(
    client: TestClient,
) -> None:
    """Milestone 3.0a's transfer records the same pair a share does -- a
    system entry and an audit row -- so the feed drops the same half
    (`activity.ACCESS_ACTIONS`)."""
    signup(client, "owner@example.com", "Owner")
    signup(client, "successor@example.com", "Successor")
    login(client, "owner@example.com")
    opportunity = create_opportunity(client)

    response = client.post(
        "/api/v2/opportunities/bulk",
        json={
            "ids": [opportunity["id"]],
            "action": "assign_owner",
            "new_owner_email": "successor@example.com",
        },
    )
    assert response.status_code == 200, response.text
    login(client, "successor@example.com")

    events = activity(client, opportunity["id"])
    assert sources(events) == ["system_entry", "system_entry"]
    assert events[1]["detail"]["title"] == "Owner changed to Successor"

    audit = client.get(f"/api/v2/opportunities/{opportunity['id']}/audit-log")
    assert [item["action"] for item in audit.json()["items"]] == ["owner_changed"]


def test_an_editor_reads_the_events_they_may_already_see(client: TestClient) -> None:
    """Each row keeps its source's rule: system entries for anyone with
    access, the audit and version halves for the owner only (invariant 7,
    D-096)."""
    signup(client, "owner@example.com", "Owner")
    signup(client, "editor@example.com", "Editor")
    login(client, "owner@example.com")
    opportunity = create_opportunity(client)
    entry_id = create_entry(client, opportunity["id"])
    assert (
        client.post(
            f"/api/v2/opportunities/{opportunity['id']}/shares",
            json={"email": "editor@example.com", "role": "editor"},
        )
    ).status_code == 201
    assert (
        client.patch(f"/api/v2/opportunities/{opportunity['id']}", json={"name": "Acme Renewal"})
    ).status_code == 200
    assert client.delete(f"/api/v2/timeline/{entry_id}").status_code == 204

    owner_events = activity(client, opportunity["id"])
    assert set(sources(owner_events)) == {"system_entry", "audit_log", "version"}

    login(client, "editor@example.com")
    editor_events = activity(client, opportunity["id"])

    assert set(sources(editor_events)) == {"system_entry"}
    assert editor_events == [
        event for event in owner_events if event["detail"]["source"] == "system_entry"
    ]


def test_the_feed_is_chronological_and_its_ids_are_unique(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry_id = create_entry(client, opportunity["id"])
    add_note(client, entry_id)
    for name in ("Acme Renewal", "Acme Renewal II", "Acme Renewal III"):
        assert (
            client.patch(f"/api/v2/opportunities/{opportunity['id']}", json={"name": name})
        ).status_code == 200

    events = activity(client, opportunity["id"])
    keys = [(event["occurred_at"], event["id"]) for event in events]

    assert keys == sorted(keys)
    assert len(set(event["id"] for event in events)) == len(events)


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_walking_the_cursor_yields_every_event_exactly_once(
    client: TestClient,
    limit: int,
) -> None:
    """The merge takes `limit + 1` rows from each source, so a page boundary
    that falls inside one source must not drop the others' rows around it."""
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry_id = create_entry(client, opportunity["id"])
    note_id = add_note(client, entry_id)
    assert (
        client.patch(f"/api/v2/opportunities/{opportunity['id']}", json={"stage": "Proposal"})
    ).status_code == 200
    assert (
        client.patch(f"/api/v2/timeline/{entry_id}", json={"title": "Discovery call (2)"})
    ).status_code == 200
    assert (edit_note(client, note_id, "Second draft")).status_code == 200
    assert client.delete(f"/api/v2/notes/{note_id}").status_code == 204

    whole = activity(client, opportunity["id"])

    walked: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        query = f"?limit={limit}" + (f"&cursor={cursor}" if cursor else "")
        response = client.get(f"/api/v2/opportunities/{opportunity['id']}/activity{query}")
        assert response.status_code == 200, response.text
        payload = response.json()
        assert len(payload["items"]) <= limit
        walked.extend(payload["items"])
        cursor = payload["next_cursor"]
        if cursor is None:
            break

    assert walked == whole


def test_events_from_one_action_read_in_the_order_it_performed_them(
    client: TestClient,
) -> None:
    """Every timestamp this app writes is second-resolution (D-067), so a
    create, an edit and a delete a moment apart carry the same `occurred_at`.
    The id's leading rank is what orders them then, and it is ranked so that
    the answer is the order the action actually performed them."""
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry_id = create_entry(client, opportunity["id"])
    assert (
        client.patch(f"/api/v2/opportunities/{opportunity['id']}", json={"name": "Renamed"})
    ).status_code == 200
    assert client.delete(f"/api/v2/timeline/{entry_id}").status_code == 204

    events = activity(client, opportunity["id"])
    stamps = {event["occurred_at"] for event in events}

    assert len(stamps) == 1, "the whole test ran inside one second"
    assert sources(events) == ["system_entry", "version", "audit_log"]


def test_the_id_separates_the_five_sources_it_merges(client: TestClient) -> None:
    """The five tables have five independent id spaces and the feed needs one
    that is unique and ordered across all of them. `ACTIVITY_STRIDE` is how far
    apart they are held; this is what fails if a row id ever reaches into the
    next source's range, which is the assumption the encoding rests on."""
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry_id = create_entry(client, opportunity["id"])
    note_id = add_note(client, entry_id)
    # Deleted last, and a comment rather than anything versioned: a delete
    # that cascades takes its children's edits out of the feed with it, which
    # `test_an_edit_to_something_since_deleted_leaves_the_feed` covers and
    # this one would only be confused by.
    comment_id = add_comment(client, note_id)
    for json_body, path in (
        ({"name": "Renamed"}, f"/api/v2/opportunities/{opportunity['id']}"),
        ({"title": "Second call"}, f"/api/v2/timeline/{entry_id}"),
    ):
        assert client.patch(path, json=json_body).status_code == 200
    assert edit_note(client, note_id, "Second draft").status_code == 200
    assert client.delete(f"/api/v2/comments/{comment_id}").status_code == 204

    events = activity(client, opportunity["id"])

    assert {event["id"] // ACTIVITY_STRIDE for event in events} == set(SOURCE_RANKS.values())
    # Every id sits inside its own source's range, which is the assumption
    # that makes one merged order out of five independent id spaces.
    for event in events:
        assert 0 < event["id"] % ACTIVITY_STRIDE < ACTIVITY_STRIDE


def test_a_reader_without_access_is_told_nothing(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    signup(client, "outsider@example.com", "Outsider")

    response = client.get(f"/api/v2/opportunities/{opportunity['id']}/activity")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
