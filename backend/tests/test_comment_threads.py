"""Threaded comments and resolve/unresolve (milestone 3.3).

`docs/FEATURES.md` §7 asks for a discussion that stays readable: a reply that
is visibly an answer rather than another comment, and a way to say a thread is
finished. Both are additions to the `comments` table rather than a new one
(revision `20260924_0007_comment_threads`), so what needs proving is the rules
around them — one level of depth, the cascade a thread now carries, and who
may declare it resolved.

The immutability half is in `test_invariants.py`: a body still cannot be
edited through any method, and resolving deliberately does not change one.
"""

from fastapi.testclient import TestClient
from test_timeline import (
    create_entry,
    create_opportunity,
    login,
    share_opportunity,
    signup,
)

from app.database import db_connection


def create_note(client: TestClient, entry_id: int, body: str = "Owner note") -> dict:
    response = client.post(f"/api/v2/timeline/{entry_id}/notes", json={"body": body})
    assert response.status_code == 201
    return response.json()


def post_comment(
    client: TestClient,
    note_id: int,
    body: str,
    parent_id: int | None = None,
) -> dict:
    payload: dict[str, object] = {"body": body}
    if parent_id is not None:
        payload["parent_id"] = parent_id
    response = client.post(f"/api/v2/notes/{note_id}/comments", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def read_threads(client: TestClient, opportunity_id: int, entry_id: int) -> list[dict]:
    timeline = client.get(f"/api/v2/opportunities/{opportunity_id}/timeline")
    assert timeline.status_code == 200
    entry = next(item for item in timeline.json()["items"] if item["id"] == entry_id)
    return entry["notes"][0]["comments"]


def setup_note(client: TestClient) -> tuple[dict, dict, dict]:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    return opportunity, entry, create_note(client, entry["id"])


def test_a_reply_is_read_under_the_comment_it_answers(client: TestClient) -> None:
    opportunity, entry, note = setup_note(client)

    question = post_comment(client, note["id"], "What is their budget?")
    answer = post_comment(client, note["id"], "Around 25k", parent_id=question["id"])
    separate = post_comment(client, note["id"], "Unrelated point")

    assert answer["parent_id"] == question["id"]

    threads = read_threads(client, opportunity["id"], entry["id"])
    assert [thread["id"] for thread in threads] == [question["id"], separate["id"]]
    assert [reply["id"] for reply in threads[0]["replies"]] == [answer["id"]]
    assert threads[1]["replies"] == []
    # A thread nobody has finished reads as open, with nobody named.
    assert threads[0]["resolved_at"] is None
    assert threads[0]["resolved_by_name"] is None


def test_threading_stops_at_one_level(client: TestClient) -> None:
    """A reply to a reply is refused rather than quietly reparented (D-127)."""
    _, _, note = setup_note(client)

    question = post_comment(client, note["id"], "What is their budget?")
    answer = post_comment(client, note["id"], "Around 25k", parent_id=question["id"])

    nested = client.post(
        f"/api/v2/notes/{note['id']}/comments",
        json={"body": "And the timing?", "parent_id": answer["id"]},
    )
    assert nested.status_code == 400
    assert nested.json()["error"]["code"] == "bad_request"


def test_a_reply_cannot_cross_to_another_note(client: TestClient) -> None:
    _, entry, note = setup_note(client)
    other_note = create_note(client, entry["id"], body="Second note")

    comment = post_comment(client, note["id"], "On the first note")

    misplaced = client.post(
        f"/api/v2/notes/{other_note['id']}/comments",
        json={"body": "Wrong note", "parent_id": comment["id"]},
    )
    assert misplaced.status_code == 404


def test_replying_notifies_the_comments_author_and_the_notes(client: TestClient) -> None:
    """Two people are addressed by a reply, and each is told once."""
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    note = create_note(client, entry["id"])
    client.post("/api/v2/auth/logout")

    asker = signup(client, "asker@example.com", "Asker")
    client.post("/api/v2/auth/logout")
    replier = signup(client, "replier@example.com", "Replier")
    client.post("/api/v2/auth/logout")
    share_opportunity(opportunity["id"], asker["id"], owner["id"], "editor")
    share_opportunity(opportunity["id"], replier["id"], owner["id"], "editor")

    login(client, "asker@example.com")
    question = post_comment(client, note["id"], "What is their budget?")
    client.post("/api/v2/auth/logout")

    login(client, "replier@example.com")
    post_comment(client, note["id"], "Around 25k", parent_id=question["id"])
    client.post("/api/v2/auth/logout")

    login(client, "asker@example.com")
    asker_inbox = client.get("/api/v2/notifications?type=comment").json()["items"]
    assert len(asker_inbox) == 1
    client.post("/api/v2/auth/logout")

    # The note's author is told as well, and — being the author of neither
    # comment — told once per comment rather than twice for the reply.
    login(client, "owner@example.com")
    owner_inbox = client.get("/api/v2/notifications?type=comment").json()["items"]
    assert len(owner_inbox) == 2


def test_replying_to_your_own_note_notifies_you_once(client: TestClient) -> None:
    """The note's author and the parent comment's author can be one person."""
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    note = create_note(client, entry["id"])
    question = post_comment(client, note["id"], "What is their budget?")
    client.post("/api/v2/auth/logout")

    editor = signup(client, "editor@example.com", "Editor")
    client.post("/api/v2/auth/logout")
    share_opportunity(opportunity["id"], editor["id"], owner["id"], "editor")

    login(client, "editor@example.com")
    post_comment(client, note["id"], "Around 25k", parent_id=question["id"])
    client.post("/api/v2/auth/logout")

    login(client, "owner@example.com")
    inbox = client.get("/api/v2/notifications?type=comment").json()["items"]
    assert len(inbox) == 1


def test_resolving_records_who_finished_the_thread(client: TestClient) -> None:
    opportunity, entry, note = setup_note(client)
    question = post_comment(client, note["id"], "What is their budget?")
    post_comment(client, note["id"], "Around 25k", parent_id=question["id"])

    resolved = client.post(f"/api/v2/comments/{question['id']}/resolve")
    assert resolved.status_code == 200
    assert resolved.json()["resolved_by_name"] == "Owner"
    assert resolved.json()["resolved_at"] is not None
    # The whole thread comes back, not just the row that changed.
    assert len(resolved.json()["replies"]) == 1

    threads = read_threads(client, opportunity["id"], entry["id"])
    assert threads[0]["resolved_by_name"] == "Owner"

    reopened = client.post(f"/api/v2/comments/{question['id']}/unresolve")
    assert reopened.status_code == 200
    assert reopened.json()["resolved_at"] is None
    assert reopened.json()["resolved_by"] is None


def test_resolving_twice_keeps_the_first_resolver(client: TestClient) -> None:
    """Both directions are idempotent, so a retry is safe (D-128)."""
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    note = create_note(client, entry["id"])
    client.post("/api/v2/auth/logout")

    editor = signup(client, "editor@example.com", "Editor")
    client.post("/api/v2/auth/logout")
    share_opportunity(opportunity["id"], editor["id"], owner["id"], "editor")

    login(client, "editor@example.com")
    question = post_comment(client, note["id"], "What is their budget?")
    first = client.post(f"/api/v2/comments/{question['id']}/resolve").json()
    client.post("/api/v2/auth/logout")

    login(client, "owner@example.com")
    second = client.post(f"/api/v2/comments/{question['id']}/resolve").json()
    assert second["resolved_by"] == first["resolved_by"]
    assert second["resolved_at"] == first["resolved_at"]
    assert second["resolved_by_name"] == "Editor"

    # And unresolving something already open changes nothing either.
    client.post(f"/api/v2/comments/{question['id']}/unresolve")
    reopened_again = client.post(f"/api/v2/comments/{question['id']}/unresolve")
    assert reopened_again.status_code == 200
    assert reopened_again.json()["resolved_at"] is None


def test_resolving_is_author_or_owner_only(client: TestClient) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    note = create_note(client, entry["id"])
    question = post_comment(client, note["id"], "What is their budget?")
    client.post("/api/v2/auth/logout")

    editor = signup(client, "editor@example.com", "Editor")
    client.post("/api/v2/auth/logout")
    viewer = signup(client, "viewer@example.com", "Viewer")
    client.post("/api/v2/auth/logout")
    share_opportunity(opportunity["id"], editor["id"], owner["id"], "editor")
    share_opportunity(opportunity["id"], viewer["id"], owner["id"], "viewer")

    login(client, "editor@example.com")
    assert client.post(f"/api/v2/comments/{question['id']}/resolve").status_code == 403
    client.post("/api/v2/auth/logout")

    login(client, "viewer@example.com")
    assert client.post(f"/api/v2/comments/{question['id']}/resolve").status_code == 403
    client.post("/api/v2/auth/logout")

    # The author of a thread may close their own question even when the deal
    # is not theirs.
    login(client, "editor@example.com")
    own_thread = post_comment(client, note["id"], "Who signs this?")
    assert client.post(f"/api/v2/comments/{own_thread['id']}/resolve").status_code == 200


def test_a_reply_cannot_be_resolved_on_its_own(client: TestClient) -> None:
    _, _, note = setup_note(client)
    question = post_comment(client, note["id"], "What is their budget?")
    answer = post_comment(client, note["id"], "Around 25k", parent_id=question["id"])

    refused = client.post(f"/api/v2/comments/{answer['id']}/resolve")
    assert refused.status_code == 400
    assert "thread" in refused.json()["error"]["message"]


def test_resolving_an_unknown_or_deleted_thread_is_404(client: TestClient) -> None:
    _, _, note = setup_note(client)
    question = post_comment(client, note["id"], "What is their budget?")
    assert client.delete(f"/api/v2/comments/{question['id']}").status_code == 204

    assert client.post(f"/api/v2/comments/{question['id']}/resolve").status_code == 404
    assert client.post("/api/v2/comments/9999/resolve").status_code == 404


def test_deleting_a_thread_takes_its_replies_and_undo_brings_both_back(
    client: TestClient,
) -> None:
    opportunity, entry, note = setup_note(client)
    question = post_comment(client, note["id"], "What is their budget?")
    answer = post_comment(client, note["id"], "Around 25k", parent_id=question["id"])
    other = post_comment(client, note["id"], "Separate thread")

    assert client.delete(f"/api/v2/comments/{question['id']}").status_code == 204
    assert [thread["id"] for thread in read_threads(client, opportunity["id"], entry["id"])] == [
        other["id"]
    ]
    with db_connection() as connection:
        deleted = connection.execute(
            "SELECT deleted_at FROM comments WHERE id IN (?, ?)",
            (question["id"], answer["id"]),
        ).fetchall()
    assert [row["deleted_at"] for row in deleted] == [deleted[0]["deleted_at"]] * 2

    assert client.post(f"/api/v2/comments/{question['id']}/restore").status_code == 204
    threads = read_threads(client, opportunity["id"], entry["id"])
    assert [thread["id"] for thread in threads] == [question["id"], other["id"]]
    assert [reply["id"] for reply in threads[0]["replies"]] == [answer["id"]]


def test_a_reply_deleted_on_its_own_stays_deleted_when_the_thread_returns(
    client: TestClient,
) -> None:
    """The stamp scopes a restore, here as everywhere else (D-067)."""
    opportunity, entry, note = setup_note(client)
    question = post_comment(client, note["id"], "What is their budget?")
    kept = post_comment(client, note["id"], "Around 25k", parent_id=question["id"])
    withdrawn = post_comment(client, note["id"], "Ignore that", parent_id=question["id"])

    assert client.delete(f"/api/v2/comments/{withdrawn['id']}").status_code == 204
    # A second apart in the stamp is not guaranteed, so separate the two
    # deletes by writing a distinguishable one directly.
    with db_connection() as connection:
        connection.execute(
            "UPDATE comments SET deleted_at = ? WHERE id = ?",
            ("2026-01-01T00:00:00Z", withdrawn["id"]),
        )
        connection.commit()

    assert client.delete(f"/api/v2/comments/{question['id']}").status_code == 204
    assert client.post(f"/api/v2/comments/{question['id']}/restore").status_code == 204

    threads = read_threads(client, opportunity["id"], entry["id"])
    assert [reply["id"] for reply in threads[0]["replies"]] == [kept["id"]]


def test_a_reply_under_a_deleted_thread_cannot_be_restored_alone(
    client: TestClient,
) -> None:
    _, _, note = setup_note(client)
    question = post_comment(client, note["id"], "What is their budget?")
    answer = post_comment(client, note["id"], "Around 25k", parent_id=question["id"])

    assert client.delete(f"/api/v2/comments/{answer['id']}").status_code == 204
    assert client.delete(f"/api/v2/comments/{question['id']}").status_code == 204

    assert client.post(f"/api/v2/comments/{answer['id']}/restore").status_code == 404


def test_a_reply_is_searchable_and_leaves_the_index_when_its_thread_goes(
    client: TestClient,
) -> None:
    """The FTS5 triggers already cover this; the cascade is what is new."""
    _, _, note = setup_note(client)
    question = post_comment(client, note["id"], "What is their budget?")
    post_comment(client, note["id"], "Procurement signs in March", parent_id=question["id"])

    found = client.get("/api/v2/search?q=procurement").json()["items"]
    assert [item["kind"] for item in found] == ["comment"]

    assert client.delete(f"/api/v2/comments/{question['id']}").status_code == 204
    assert client.get("/api/v2/search?q=procurement").json()["items"] == []
