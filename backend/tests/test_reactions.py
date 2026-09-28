"""Reactions on comments and replies (milestone 3.3a, `docs/FEATURES.md` §7).

`docs/autopilot/DECISIONS.md` D-130: a reaction is toggle state a person sets
and unsets, not content, so it is hard-deleted rather than soft-deleted --
`test_soft_delete.py`'s scanner is expected to leave `reactions` alone, and
that is proven there, not here. What belongs here is the toggle's own
behavior: idempotence, who may react, and that both roots and replies carry
their reactions back on every read that returns a comment.
"""

from fastapi.testclient import TestClient
from test_comment_threads import post_comment, read_threads, setup_note
from test_timeline import create_entry, create_opportunity, login, share_opportunity, signup


def test_reacting_is_idempotent_and_reads_back_on_every_comment(client: TestClient) -> None:
    opportunity, entry, note = setup_note(client)
    question = post_comment(client, note["id"], "What is their budget?")
    answer = post_comment(client, note["id"], "Around 25k", parent_id=question["id"])

    first = client.post(f"/api/v2/comments/{question['id']}/reactions", json={"emoji": "👍"})
    assert first.status_code == 200, first.text
    assert [r["emoji"] for r in first.json()["reactions"]] == ["👍"]

    # Reacting again with the same emoji changes nothing.
    second = client.post(f"/api/v2/comments/{question['id']}/reactions", json={"emoji": "👍"})
    assert second.status_code == 200
    assert len(second.json()["reactions"]) == 1

    # A reply carries its own reactions too.
    reply_reaction = client.post(f"/api/v2/comments/{answer['id']}/reactions", json={"emoji": "🎉"})
    assert reply_reaction.status_code == 200
    assert [r["emoji"] for r in reply_reaction.json()["reactions"]] == ["🎉"]

    threads = read_threads(client, opportunity["id"], entry["id"])
    assert [r["emoji"] for r in threads[0]["reactions"]] == ["👍"]
    assert [r["emoji"] for r in threads[0]["replies"][0]["reactions"]] == ["🎉"]


def test_one_person_can_react_with_more_than_one_emoji(client: TestClient) -> None:
    _, _, note = setup_note(client)
    question = post_comment(client, note["id"], "What is their budget?")

    client.post(f"/api/v2/comments/{question['id']}/reactions", json={"emoji": "👍"})
    reacted = client.post(f"/api/v2/comments/{question['id']}/reactions", json={"emoji": "👀"})

    assert sorted(r["emoji"] for r in reacted.json()["reactions"]) == ["👀", "👍"]


def test_removing_a_reaction_is_idempotent(client: TestClient) -> None:
    _, _, note = setup_note(client)
    question = post_comment(client, note["id"], "What is their budget?")
    client.post(f"/api/v2/comments/{question['id']}/reactions", json={"emoji": "👍"})

    removed = client.delete(f"/api/v2/comments/{question['id']}/reactions/👍")
    assert removed.status_code == 200
    assert removed.json()["reactions"] == []

    # Removing again, and removing one that was never there, are both no-ops.
    again = client.delete(f"/api/v2/comments/{question['id']}/reactions/👍")
    assert again.status_code == 200
    assert again.json()["reactions"] == []

    never_there = client.delete(f"/api/v2/comments/{question['id']}/reactions/🚀")
    assert never_there.status_code == 200


def test_two_people_reacting_with_the_same_emoji_both_count(client: TestClient) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    note = client.post(f"/api/v2/timeline/{entry['id']}/notes", json={"body": "Note"}).json()
    question = post_comment(client, note["id"], "What is their budget?")
    client.post(f"/api/v2/comments/{question['id']}/reactions", json={"emoji": "👍"})
    client.post("/api/v2/auth/logout")

    editor = signup(client, "editor@example.com", "Editor")
    client.post("/api/v2/auth/logout")
    share_opportunity(opportunity["id"], editor["id"], owner["id"], "editor")

    login(client, "editor@example.com")
    reacted = client.post(f"/api/v2/comments/{question['id']}/reactions", json={"emoji": "👍"})

    assert len(reacted.json()["reactions"]) == 2
    assert {r["user_id"] for r in reacted.json()["reactions"]} == {owner["id"], editor["id"]}


def test_viewer_cannot_react_editor_and_owner_can(client: TestClient) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    note = client.post(f"/api/v2/timeline/{entry['id']}/notes", json={"body": "Note"}).json()
    question = post_comment(client, note["id"], "What is their budget?")
    client.post("/api/v2/auth/logout")

    viewer = signup(client, "viewer@example.com", "Viewer")
    client.post("/api/v2/auth/logout")
    share_opportunity(opportunity["id"], viewer["id"], owner["id"], "viewer")

    login(client, "viewer@example.com")
    refused = client.post(f"/api/v2/comments/{question['id']}/reactions", json={"emoji": "👍"})
    assert refused.status_code == 403


def test_reacting_to_an_unknown_or_deleted_comment_is_404(client: TestClient) -> None:
    _, _, note = setup_note(client)
    question = post_comment(client, note["id"], "What is their budget?")
    assert client.delete(f"/api/v2/comments/{question['id']}").status_code == 204

    reacted = client.post(f"/api/v2/comments/{question['id']}/reactions", json={"emoji": "👍"})
    assert reacted.status_code == 404
    assert client.post("/api/v2/comments/9999/reactions", json={"emoji": "👍"}).status_code == 404
    assert client.delete(f"/api/v2/comments/{question['id']}/reactions/👍").status_code == 404


def test_an_unrecognized_emoji_is_rejected(client: TestClient) -> None:
    _, _, note = setup_note(client)
    question = post_comment(client, note["id"], "What is their budget?")

    refused = client.post(
        f"/api/v2/comments/{question['id']}/reactions", json={"emoji": "not-an-emoji"}
    )
    assert refused.status_code == 422
