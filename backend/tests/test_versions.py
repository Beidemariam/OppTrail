"""Edit history for the three editable things (milestone 2.10).

`AGENTS.md` invariant 8: an edit records what it replaced. Notes have done that
since the baseline; this suite is what holds opportunities and timeline entries
to the same rule, and holds all three to one shape — version 1 is the state the
thing was created in, every edit appends the whole resulting state, and nothing
is ever overwritten.

The read side is owner-only (D-096); the authorization matrix
(`test_authorization_matrix.py`) owns the per-actor answers, so what is checked
here is the content.
"""

from fastapi.testclient import TestClient

from app.database import db_connection


def signup(client: TestClient, email: str = "owner@example.com", name: str = "Owner") -> int:
    response = client.post(
        "/api/v2/auth/signup",
        json={"email": email, "password": "password123", "name": name},
    )
    assert response.status_code == 201
    user_id: int = response.json()["user"]["id"]
    return user_id


def create_opportunity(client: TestClient, name: str = "Expansion") -> dict:
    response = client.post(
        "/api/v2/opportunities",
        json={
            "name": name,
            "account_name": "Acme",
            "value": "485000",
            "currency": "USD",
            "stage": "Proposal",
            "expected_close_date": "2026-11-30",
        },
    )
    assert response.status_code == 201
    return dict(response.json())


def create_entry(client: TestClient, opportunity_id: int) -> dict:
    response = client.post(
        f"/api/v2/opportunities/{opportunity_id}/timeline",
        json={
            "type": "call",
            "title": "Discovery call",
            "body": "Walked the procurement process.",
            "event_timestamp": "2026-09-04T10:00:00Z",
        },
    )
    assert response.status_code == 201
    return dict(response.json())


def versions(client: TestClient, path: str) -> list[dict]:
    response = client.get(path)
    assert response.status_code == 200, response.text
    items: list[dict] = response.json()["items"]
    return items


def test_creating_an_opportunity_records_the_state_it_was_created_in(
    client: TestClient,
) -> None:
    user_id = signup(client)
    opportunity = create_opportunity(client)

    history = versions(client, f"/api/v2/opportunities/{opportunity['id']}/versions")

    assert len(history) == 1
    assert history[0]["version_number"] == 1
    assert history[0]["value"] == "485000"
    assert history[0]["stage"] == "Proposal"
    assert history[0]["edited_by"] == user_id
    assert history[0]["editor_name"] == "Owner"
    # The record and its first version agree on when it appeared, so a reader
    # comparing the two never sees the history start after the thing did.
    assert history[0]["created_at"] == opportunity["created_at"]


def test_editing_an_opportunity_keeps_the_value_it_replaced(client: TestClient) -> None:
    """The case that prompted the requirement: a deal dropping from 485,000 to
    250,000 used to leave no trace of the number it had been."""
    signup(client)
    opportunity = create_opportunity(client)

    response = client.patch(
        f"/api/v2/opportunities/{opportunity['id']}",
        json={"value": "250000"},
    )
    assert response.status_code == 200

    history = versions(client, f"/api/v2/opportunities/{opportunity['id']}/versions")

    assert [version["version_number"] for version in history] == [1, 2]
    assert [version["value"] for version in history] == ["485000", "250000"]
    # A PATCH carries only what changed; a version is the whole state, so the
    # fields the request left alone are still readable at every point.
    assert history[1]["name"] == "Expansion"
    assert history[1]["stage"] == "Proposal"
    assert history[1]["expected_close_date"] == "2026-11-30"


def test_an_opportunity_version_carries_the_rows_own_timestamp(client: TestClient) -> None:
    signup(client)
    opportunity = create_opportunity(client)
    updated = client.patch(
        f"/api/v2/opportunities/{opportunity['id']}",
        json={"name": "Expansion, phase two"},
    )
    assert updated.status_code == 200

    history = versions(client, f"/api/v2/opportunities/{opportunity['id']}/versions")

    assert history[-1]["created_at"] == updated.json()["updated_at"]


def test_a_stage_set_in_bulk_is_recorded_like_any_other_edit(client: TestClient) -> None:
    signup(client)
    first = create_opportunity(client, "First")
    second = create_opportunity(client, "Second")

    response = client.post(
        "/api/v2/opportunities/bulk",
        json={"ids": [first["id"], second["id"]], "action": "set_stage", "stage": "Negotiation"},
    )
    assert response.status_code == 200

    for opportunity in (first, second):
        history = versions(client, f"/api/v2/opportunities/{opportunity['id']}/versions")
        assert [version["stage"] for version in history] == ["Proposal", "Negotiation"]


def test_editing_a_timeline_entry_keeps_what_it_replaced(client: TestClient) -> None:
    signup(client)
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])

    response = client.patch(
        f"/api/v2/timeline/{entry['id']}",
        json={"title": "Discovery call, corrected", "event_timestamp": "2026-09-05T09:30:00Z"},
    )
    assert response.status_code == 200

    history = versions(client, f"/api/v2/timeline/{entry['id']}/versions")

    assert [version["version_number"] for version in history] == [1, 2]
    assert [version["title"] for version in history] == [
        "Discovery call",
        "Discovery call, corrected",
    ]
    assert [version["event_timestamp"] for version in history] == [
        "2026-09-04T10:00:00Z",
        "2026-09-05T09:30:00Z",
    ]
    # Untouched by the PATCH, and still part of every snapshot.
    assert history[1]["body"] == "Walked the procurement process."
    assert history[1]["type"] == "call"


def test_a_patch_that_changes_nothing_records_nothing(client: TestClient) -> None:
    """An empty PATCH writes no row, so a client that saves an unchanged form
    does not pad the history with copies."""
    signup(client)
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])

    assert client.patch(f"/api/v2/timeline/{entry['id']}", json={}).status_code == 200

    assert len(versions(client, f"/api/v2/timeline/{entry['id']}/versions")) == 1


def test_a_system_entry_has_no_history_to_show(client: TestClient) -> None:
    """System entries cannot be edited (`AGENTS.md`, auditability), so their
    history is empty rather than a copy of the row beside it."""
    signup(client)
    opportunity = create_opportunity(client)

    timeline = client.get(f"/api/v2/opportunities/{opportunity['id']}/timeline")
    assert timeline.status_code == 200
    created_entry = next(entry for entry in timeline.json()["items"] if entry["system_generated"])

    assert versions(client, f"/api/v2/timeline/{created_entry['id']}/versions") == []


def test_note_history_still_reads_forwards(client: TestClient) -> None:
    signup(client)
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    note = client.post(
        f"/api/v2/timeline/{entry['id']}/notes",
        json={"body": "First draft"},
    )
    assert note.status_code == 201
    note_id = note.json()["id"]
    assert (
        client.patch(f"/api/v2/notes/{note_id}", json={"body": "Second draft"}).status_code == 200
    )

    history = versions(client, f"/api/v2/notes/{note_id}/versions")

    assert [(version["version_number"], version["body"]) for version in history] == [
        (1, "First draft"),
        (2, "Second draft"),
    ]


def test_history_is_paginated_oldest_first(client: TestClient) -> None:
    signup(client)
    opportunity = create_opportunity(client)
    for stage in ("Qualification", "Needs Analysis", "Negotiation"):
        assert (
            client.patch(
                f"/api/v2/opportunities/{opportunity['id']}", json={"stage": stage}
            ).status_code
            == 200
        )

    first = client.get(f"/api/v2/opportunities/{opportunity['id']}/versions?limit=2")
    assert first.status_code == 200
    assert [item["version_number"] for item in first.json()["items"]] == [1, 2]

    cursor = first.json()["next_cursor"]
    assert cursor
    second = client.get(
        f"/api/v2/opportunities/{opportunity['id']}/versions?limit=2&cursor={cursor}"
    )
    assert second.status_code == 200
    assert [item["version_number"] for item in second.json()["items"]] == [3, 4]
    assert second.json()["next_cursor"] is None


def test_history_survives_a_delete_and_a_restore(client: TestClient) -> None:
    """Undo puts the row back, and the versions it had are still there: nothing
    in the delete path touches them (`app/soft_delete.py` stamps, never
    removes)."""
    signup(client)
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    assert (
        client.patch(f"/api/v2/timeline/{entry['id']}", json={"title": "Edited"}).status_code == 200
    )
    assert client.delete(f"/api/v2/timeline/{entry['id']}").status_code == 204
    assert client.post(f"/api/v2/timeline/{entry['id']}/restore").status_code == 204

    assert [
        version["title"] for version in versions(client, f"/api/v2/timeline/{entry['id']}/versions")
    ] == ["Discovery call", "Edited"]


def test_versions_are_numbered_without_gaps_under_the_unique_index(client: TestClient) -> None:
    """The number comes out of the table rather than from a counter the caller
    keeps, and `UNIQUE (parent, version_number)` is what makes that safe."""
    signup(client)
    opportunity = create_opportunity(client)
    for value in ("400000", "350000", "300000"):
        assert (
            client.patch(
                f"/api/v2/opportunities/{opportunity['id']}", json={"value": value}
            ).status_code
            == 200
        )

    with db_connection() as connection:
        numbers = [
            row["version_number"]
            for row in connection.execute(
                "SELECT version_number FROM opportunity_versions "
                "WHERE opportunity_id = ? ORDER BY version_number",
                (opportunity["id"],),
            )
        ]

    assert numbers == [1, 2, 3, 4]


# --- Restoring a version (milestone 3.1c, D-116 / D-120) --------------------
#
# The existing `POST /<kind>/{id}/restore` routes undo a soft delete. These
# undo an *edit*: they write a recorded version back over the live row. The
# rule the whole group turns on is that restoring is itself an edit, so the
# history only ever grows and a restore can be restored from.


def test_restoring_an_opportunity_version_brings_the_old_values_back(
    client: TestClient,
) -> None:
    signup(client)
    opportunity = create_opportunity(client)
    assert (
        client.patch(
            f"/api/v2/opportunities/{opportunity['id']}",
            json={"value": "250000", "name": "Expansion, trimmed"},
        ).status_code
        == 200
    )

    restored = client.post(f"/api/v2/opportunities/{opportunity['id']}/versions/1/restore")

    assert restored.status_code == 200
    assert restored.json()["value"] == "485000"
    assert restored.json()["name"] == "Expansion"


def test_restoring_appends_a_version_rather_than_truncating_the_history(
    client: TestClient,
) -> None:
    """The property that makes a restore safe: nothing recorded is removed, so
    the state the restore replaced is itself recoverable."""
    signup(client)
    opportunity = create_opportunity(client)
    assert (
        client.patch(
            f"/api/v2/opportunities/{opportunity['id']}", json={"value": "250000"}
        ).status_code
        == 200
    )

    assert (
        client.post(f"/api/v2/opportunities/{opportunity['id']}/versions/1/restore").status_code
        == 200
    )

    history = versions(client, f"/api/v2/opportunities/{opportunity['id']}/versions")
    assert [(version["version_number"], version["value"]) for version in history] == [
        (1, "485000"),
        (2, "250000"),
        (3, "485000"),
    ]

    # And the restore is itself restorable, which is what "never destructive"
    # has to mean: version 2 is still there to go back to.
    assert (
        client.post(f"/api/v2/opportunities/{opportunity['id']}/versions/2/restore").status_code
        == 200
    )
    assert [
        version["value"]
        for version in versions(client, f"/api/v2/opportunities/{opportunity['id']}/versions")
    ] == ["485000", "250000", "485000", "250000"]


def test_restoring_a_stage_narrates_it_on_the_timeline(client: TestClient) -> None:
    """Every stage change writes the same system entry, including the one a
    restore performs — otherwise the timeline and the record disagree."""
    signup(client)
    opportunity = create_opportunity(client)
    assert (
        client.patch(
            f"/api/v2/opportunities/{opportunity['id']}", json={"stage": "Negotiation"}
        ).status_code
        == 200
    )

    assert (
        client.post(f"/api/v2/opportunities/{opportunity['id']}/versions/1/restore").status_code
        == 200
    )

    timeline = client.get(f"/api/v2/opportunities/{opportunity['id']}/timeline")
    assert timeline.status_code == 200
    stage_entries = [
        entry["body"] for entry in timeline.json()["items"] if entry["type"] == "stage_change"
    ]
    assert stage_entries == [
        "Stage changed from Proposal to Negotiation.",
        "Stage changed from Negotiation to Proposal.",
    ]


def test_restoring_what_is_already_current_writes_nothing(client: TestClient) -> None:
    """The server's half of D-114: an edit that changes nothing records
    nothing, so restoring twice does not pad the history with copies."""
    signup(client)
    opportunity = create_opportunity(client)
    assert (
        client.patch(
            f"/api/v2/opportunities/{opportunity['id']}", json={"value": "250000"}
        ).status_code
        == 200
    )

    for _ in range(2):
        assert (
            client.post(f"/api/v2/opportunities/{opportunity['id']}/versions/1/restore").status_code
            == 200
        )

    assert [
        version["value"]
        for version in versions(client, f"/api/v2/opportunities/{opportunity['id']}/versions")
    ] == ["485000", "250000", "485000"]


def test_restoring_a_timeline_entry_version_puts_the_body_back(client: TestClient) -> None:
    signup(client)
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    assert (
        client.patch(
            f"/api/v2/timeline/{entry['id']}",
            json={"title": "Discovery call, revised", "body": "Shorter summary."},
        ).status_code
        == 200
    )

    restored = client.post(f"/api/v2/timeline/{entry['id']}/versions/1/restore")

    assert restored.status_code == 200
    assert restored.json()["title"] == "Discovery call"
    assert restored.json()["body"] == "Walked the procurement process."
    assert [
        version["version_number"]
        for version in versions(client, f"/api/v2/timeline/{entry['id']}/versions")
    ] == [1, 2, 3]


def test_restoring_a_note_version_puts_the_text_back_and_keeps_the_marker(
    client: TestClient,
) -> None:
    """`edited` stays set: the note was edited, and a restore is another edit
    rather than a way to make one disappear."""
    signup(client)
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    note = client.post(f"/api/v2/timeline/{entry['id']}/notes", json={"body": "First draft"})
    assert note.status_code == 201
    note_id = note.json()["id"]
    assert (
        client.patch(f"/api/v2/notes/{note_id}", json={"body": "Second draft"}).status_code == 200
    )

    restored = client.post(f"/api/v2/notes/{note_id}/versions/1/restore")

    assert restored.status_code == 200
    assert restored.json()["body"] == "First draft"
    assert restored.json()["edited"] is True
    assert [
        version["body"] for version in versions(client, f"/api/v2/notes/{note_id}/versions")
    ] == ["First draft", "Second draft", "First draft"]


def test_restoring_a_version_that_was_never_recorded_is_a_404(client: TestClient) -> None:
    signup(client)
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    note = client.post(f"/api/v2/timeline/{entry['id']}/notes", json={"body": "Only draft"})
    assert note.status_code == 201

    assert (
        client.post(f"/api/v2/opportunities/{opportunity['id']}/versions/9/restore").status_code
        == 404
    )
    assert client.post(f"/api/v2/timeline/{entry['id']}/versions/9/restore").status_code == 404
    assert client.post(f"/api/v2/notes/{note.json()['id']}/versions/9/restore").status_code == 404


def test_a_restore_reaches_the_activity_log_as_the_edit_it_is(client: TestClient) -> None:
    """A restore leaves a version row, so the merged feed reports it the way it
    reports any other edit — which is true: the fields moved (D-120)."""
    signup(client)
    opportunity = create_opportunity(client)
    assert (
        client.patch(
            f"/api/v2/opportunities/{opportunity['id']}", json={"value": "250000"}
        ).status_code
        == 200
    )
    assert (
        client.post(f"/api/v2/opportunities/{opportunity['id']}/versions/1/restore").status_code
        == 200
    )

    activity = client.get(f"/api/v2/opportunities/{opportunity['id']}/activity")
    assert activity.status_code == 200
    edits = [
        event["detail"]
        for event in activity.json()["items"]
        if event["detail"]["source"] == "version"
    ]
    assert [edit["version_number"] for edit in edits] == [2, 3]
    assert all(edit["changed_fields"] == ["value"] for edit in edits)
