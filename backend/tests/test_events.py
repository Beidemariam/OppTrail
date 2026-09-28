"""The live-update stream and the note edit guard (milestone 3.4, ADR 0003).

Two features, one file, because they are the two halves of one decision: the
ADR's answer to "two people are on this deal at once" is *push an
invalidation* plus *refuse a write against a stale copy*. Neither is worth
much alone -- a stream with no guard still lets the second writer clobber the
first, and a guard with no stream makes a 409 the first thing a reader hears.

Three things about how the stream is tested:

- **The window is short on purpose.** `conftest.short_event_streams` holds
  `settings.sse_max_connection_seconds` down, because Starlette's
  `TestClient` buffers a response whole: a request to this route returns when
  the stream *ends*, not when it opens. The tests that watch a write land
  raise the window themselves.
- **Delivery is synchronised on the broker, not on a sleep.** A write
  published before its reader has subscribed reaches nobody, so the writing
  thread waits for `broker.subscriber_count` to rise rather than guessing how
  long the stream took to open (brief §6.5: no blind sleeps).
- **The reader runs in a thread.** It is blocked inside the stream for the
  whole window, so the write has to come from somewhere else -- which is also
  the shape of the thing being tested: two people, two connections.
"""

import asyncio
import threading
import time
from itertools import count
from typing import Any

import pytest
from conftest import CsrfClient
from fastapi.testclient import TestClient
from test_timeline import (
    create_entry,
    create_opportunity,
    edit_note,
    login,
    share_opportunity,
    signup,
)

from app import events
from app.events import Event, broker
from app.main import app
from app.settings import settings

# Long enough that a write made the instant the subscriber appears is never
# racing the close, short enough that a handful of these is still a suite.
DELIVERY_WINDOW_SECONDS = 1.0


class StreamReader:
    """One open SSE connection, read on its own thread.

    `open()` blocks until the server has registered the subscription, so a
    caller can write immediately afterwards and know the event has somewhere
    to go.
    """

    def __init__(self, client: TestClient, opportunity_id: int) -> None:
        self.client = client
        self.opportunity_id = opportunity_id
        self.body = ""
        self.status_code = 0
        self._thread = threading.Thread(target=self._read, daemon=True)

    def _read(self) -> None:
        response = self.client.get(f"/api/v2/opportunities/{self.opportunity_id}/events")
        self.status_code = response.status_code
        self.body = response.text

    def __enter__(self) -> "StreamReader":
        self._thread.start()
        # Not a blind wait: the request is already in flight on the thread
        # above and `broker.subscribe` is the first thing the route's
        # generator does, so this blocks on that registration and on nothing
        # else. The deadline is only there so a broken stream fails as a test
        # rather than as a hang.
        deadline = time.monotonic() + 5
        while broker.subscriber_count(self.opportunity_id) == 0:
            assert self._thread.is_alive(), "the stream request ended before it subscribed"
            assert time.monotonic() < deadline, "the stream never registered a subscriber"
            time.sleep(0.005)
        return self

    def __exit__(self, *_: Any) -> None:
        self._thread.join(timeout=DELIVERY_WINDOW_SECONDS * 10)
        assert not self._thread.is_alive(), "the stream did not close itself"


@pytest.fixture
def second_client(client: TestClient) -> Any:
    """A second session against the same app, for the other person on the deal.

    Depends on `client` so the database the `client` fixture points settings
    at is the one this session's startup initializes -- the order is not
    incidental.
    """
    with CsrfClient(app) as other:
        yield other


def opportunity_with_an_editor(
    owner_client: TestClient,
    editor_client: TestClient,
) -> dict[str, Any]:
    owner = signup(owner_client, "owner@example.com", "Owner")
    opportunity = create_opportunity(owner_client)
    editor = signup(editor_client, "editor@example.com", "Editor")
    share_opportunity(opportunity["id"], editor["id"], owner["id"], "editor")
    return opportunity


def test_the_stream_opens_with_a_ready_event(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)

    response = client.get(f"/api/v2/opportunities/{opportunity['id']}/events")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-store"
    # The reconnect advice has to precede the close, or a browser that loses
    # the connection falls back to its own default delay.
    assert response.text.startswith("retry: ")
    assert "event: ready" in response.text


def test_an_idle_stream_keeps_itself_alive_and_then_closes(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)

    response = client.get(f"/api/v2/opportunities/{opportunity['id']}/events")

    # The window is four heartbeats wide (`conftest.short_event_streams`), so
    # an idle stream is a sequence of comment lines and then an ordinary end
    # of response -- not an error, and not a connection left hanging.
    assert ": keepalive" in response.text
    assert "event: timeline.changed" not in response.text


def test_a_colleagues_write_reaches_an_open_stream(
    client: TestClient,
    second_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "sse_max_connection_seconds", DELIVERY_WINDOW_SECONDS)
    opportunity = opportunity_with_an_editor(client, second_client)

    with StreamReader(client, opportunity["id"]) as reader:
        assert (
            create_entry(second_client, opportunity["id"], title="Editor call")["title"]
            == "Editor call"
        )

    assert reader.status_code == 200
    assert "event: timeline.changed" in reader.body
    assert f'"opportunity_id": {opportunity["id"]}' in reader.body


def test_a_change_to_the_record_is_announced_as_its_own_kind(
    client: TestClient,
    second_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stage change is `opportunity.changed`, not `timeline.changed`.

    The two are different questions for the reader: the board holding this
    deal has gone stale as well as the timeline, and only one of the two
    events says so.
    """
    monkeypatch.setattr(settings, "sse_max_connection_seconds", DELIVERY_WINDOW_SECONDS)
    opportunity = opportunity_with_an_editor(client, second_client)

    with StreamReader(second_client, opportunity["id"]) as reader:
        assert (
            client.patch(
                f"/api/v2/opportunities/{opportunity['id']}",
                json={"stage": "Qualification"},
            ).status_code
            == 200
        )

    assert "event: opportunity.changed" in reader.body
    assert "event: timeline.changed" not in reader.body


def test_a_write_to_another_deal_is_not_announced_here(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "sse_max_connection_seconds", DELIVERY_WINDOW_SECONDS)
    signup(client, "owner@example.com", "Owner")
    watched = create_opportunity(client)
    other = create_opportunity(client)

    with StreamReader(client, watched["id"]) as reader:
        create_entry(client, other["id"], title="Somewhere else")

    assert "changed" not in reader.body
    assert "event: ready" in reader.body


def test_an_empty_patch_announces_nothing(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A write that wrote nothing has nothing to invalidate.

    Both `PATCH` routes short-circuit an empty body, and an event sent anyway
    would send every other reader to refetch a page that has not moved.
    """
    monkeypatch.setattr(settings, "sse_max_connection_seconds", DELIVERY_WINDOW_SECONDS)
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])

    with StreamReader(client, opportunity["id"]) as reader:
        assert (
            client.patch(f"/api/v2/opportunities/{opportunity['id']}", json={}).status_code == 200
        )
        assert client.patch(f"/api/v2/timeline/{entry['id']}", json={}).status_code == 200

    assert "changed" not in reader.body


def test_only_a_reader_of_the_opportunity_may_listen(
    client: TestClient,
    second_client: TestClient,
) -> None:
    """The same 404-not-403 rule the rest of the app has: a stream must not be
    the one place an outsider learns an id is live.
    """
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    signup(second_client, "outsider@example.com", "Outsider")

    assert second_client.get(f"/api/v2/opportunities/{opportunity['id']}/events").status_code == 404


def test_two_identical_writes_are_one_invalidation() -> None:
    """The queue coalesces, which is what bounds it.

    An event carries no information beyond "read this again", so a second
    identical one waiting behind the first would only buy the reader a
    duplicate refetch -- and an unbounded queue behind a slow client.
    """

    async def scenario() -> None:
        subscriber = broker.subscribe(7)
        try:
            broker.publish(7, "timeline.changed")
            broker.publish(7, "timeline.changed")
            first = await asyncio.wait_for(subscriber.next_event(), timeout=1)
            assert first == Event(type="timeline.changed", opportunity_id=7)
            # Both callbacks had already run by the time the get above
            # returned, so an empty queue here is the deduplication and not a
            # race with the second publish.
            assert subscriber.queue.empty()
        finally:
            broker.unsubscribe(subscriber)

    asyncio.run(scenario())
    assert broker.subscriber_count(7) == 0


def test_publishing_to_a_stream_whose_loop_has_gone_is_not_an_error() -> None:
    """The window between a reader disappearing and its `finally` running.

    `call_soon_threadsafe` on a closed loop raises, and a publisher that let
    that escape would fail the *writer's* request because someone else's
    browser closed a tab.
    """
    loop = asyncio.new_event_loop()

    async def register() -> events._Subscriber:
        return broker.subscribe(11)

    subscriber = loop.run_until_complete(register())
    loop.close()

    try:
        broker.publish(11, "timeline.changed")
    finally:
        broker.unsubscribe(subscriber)


# --- The note edit guard (ADR 0003's conflict model) ------------------------


def test_a_note_edit_against_a_stale_copy_is_refused(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    note = client.post(
        f"/api/v2/timeline/{entry['id']}/notes",
        json={"body": "First draft"},
    ).json()

    conflicted = client.patch(
        f"/api/v2/notes/{note['id']}",
        json={"body": "Written against an older copy", "updated_at": "2020-01-01T00:00:00Z"},
    )

    assert conflicted.status_code == 409
    assert conflicted.json()["error"]["code"] == "conflict"
    # Refused means refused: the body is untouched and no version was written.
    assert edit_note(client, note["id"], "First draft").json()["body"] == "First draft"
    versions = client.get(f"/api/v2/notes/{note['id']}/versions").json()["items"]
    assert [version["body"] for version in versions] == ["First draft", "First draft"]


def test_the_guard_does_not_answer_before_the_permission_check(
    client: TestClient,
) -> None:
    """A viewer sending a stale timestamp is told they may not edit.

    The other order would tell someone with no write access that their copy is
    out of date, which is both the wrong answer and a hint about a note they
    cannot change.
    """
    owner = signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = create_entry(client, opportunity["id"])
    note = client.post(
        f"/api/v2/timeline/{entry['id']}/notes",
        json={"body": "First draft"},
    ).json()
    client.post("/api/v2/auth/logout")

    viewer = signup(client, "viewer@example.com", "Viewer")
    client.post("/api/v2/auth/logout")
    share_opportunity(opportunity["id"], viewer["id"], owner["id"], "viewer")
    login(client, "viewer@example.com")

    refused = client.patch(
        f"/api/v2/notes/{note['id']}",
        json={"body": "Viewer edit", "updated_at": "2020-01-01T00:00:00Z"},
    )
    assert refused.status_code == 403


def test_the_second_writer_is_the_one_refused(
    client: TestClient,
    second_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The scenario the guard exists for, end to end.

    Both people open the same note. The owner saves; the editor's copy is now
    stale and their save is refused rather than silently overwriting text
    nobody has read.

    The clock is stepped a second per write because `utc_now()` has
    second resolution: without that, two edits in one test share an
    `updated_at` and the guard has nothing to compare. That is the blind spot
    `update_note` documents, and it is the same one D-067 already accepted for
    undo -- pinned here as a deterministic clock rather than left to how fast
    the machine happens to be (brief §6.5).
    """
    opportunity = opportunity_with_an_editor(client, second_client)
    entry = create_entry(client, opportunity["id"])
    # Authored by the editor, so both people may edit it: changing an existing
    # item is the author-or-owner rule (D-005), and a note the owner wrote is
    # one the editor cannot touch at all -- which would be a 403 rather than
    # the conflict this test is about.
    note = second_client.post(
        f"/api/v2/timeline/{entry['id']}/notes",
        json={"body": "First draft"},
    ).json()
    read_by_both = note["updated_at"]

    ticks = (f"2026-09-28T12:00:{second:02d}Z" for second in count(10))
    monkeypatch.setattr("app.routes_timeline.utc_now", lambda: next(ticks))

    first = edit_note(client, note["id"], "Owner's version")
    assert first.status_code == 200
    assert first.json()["updated_at"] != read_by_both

    second = second_client.patch(
        f"/api/v2/notes/{note['id']}",
        json={"body": "Editor's version", "updated_at": read_by_both},
    )

    assert second.status_code == 409
    timeline = client.get(f"/api/v2/opportunities/{opportunity['id']}/timeline").json()["items"]
    entries = [item for item in timeline if item["id"] == entry["id"]]
    assert entries[0]["notes"][0]["body"] == "Owner's version"

    # And the editor gets through once they have read the note again.
    assert (
        second_client.patch(
            f"/api/v2/notes/{note['id']}",
            json={"body": "Editor's version", "updated_at": first.json()["updated_at"]},
        ).status_code
        == 200
    )
