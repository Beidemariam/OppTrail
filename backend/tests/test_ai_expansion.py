"""The AI expansion (milestone 6.4, `docs/FEATURES.md` §14).

Three things, and they share one property worth stating before the tests:
**none of them gives the model a way to change anything.** A scoped summary
is a narrower read, a stream is the same answer arriving sooner, and a filter
proposal is a query somebody presses Apply on. ADR 0012's rule is unchanged
and `test_ai.py::test_invariant_ai_agent_has_no_write_tools` still covers the
call.

Every test here stubs the SDK, as the rest of the AI suite does --
`conftest.no_live_network` would fail the run otherwise, which is the point
of it. The lesson D-168 left is applied where it matters: the things a stub
cannot see (a default, a serialized parameter) are asserted against the
request body or against the setting itself, not against the stub.
"""

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_tasks import create_opportunity, login, logout, share, signup

from app import ai_filters, ai_service
from app.database import db_connection
from app.settings import settings


@pytest.fixture(autouse=True)
def api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "openai_api_key", "test-key")


def entry(
    client: TestClient,
    opportunity_id: int,
    title: str,
    when: str,
) -> dict:
    response = client.post(
        f"/api/v2/opportunities/{opportunity_id}/timeline",
        json={"type": "call", "title": title, "body": "", "event_timestamp": when},
    )
    assert response.status_code == 201, response.json()
    return response.json()


def stub_answer(monkeypatch: pytest.MonkeyPatch, text: str) -> dict[str, Any]:
    """The non-streaming call, capturing what was sent."""
    captured: dict[str, Any] = {}

    class FakeResponse:
        output_text = text

    class FakeResponses:
        def create(self, **kwargs: Any) -> FakeResponse:
            captured.update(kwargs)
            return FakeResponse()

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            self.responses = FakeResponses()

    monkeypatch.setattr("app.ai_service.OpenAI", FakeClient)
    return captured


def stub_stream(monkeypatch: pytest.MonkeyPatch, deltas: list[str]) -> dict[str, Any]:
    """The streaming call, as the Responses API shapes it: an iterator of
    typed events, of which only the text deltas are the answer."""
    captured: dict[str, Any] = {}

    class Delta:
        def __init__(self, text: str) -> None:
            self.type = "response.output_text.delta"
            self.delta = text

    class Noise:
        """A reasoning or lifecycle event, which must not reach the reader."""

        type = "response.reasoning_summary_text.delta"
        delta = "thinking out loud"

    class FakeResponses:
        def create(self, **kwargs: Any) -> Iterator[Any]:
            captured.update(kwargs)
            return iter([Noise(), *[Delta(text) for text in deltas], Noise()])

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            self.responses = FakeResponses()

    monkeypatch.setattr("app.ai_service.OpenAI", FakeClient)
    return captured


def sse_events(body: str) -> list[tuple[str, str]]:
    """The stream as (event, data) pairs, rejoining multi-line payloads the
    way a browser does."""
    events = []
    for frame in body.split("\n\n"):
        if not frame.strip():
            continue
        name = ""
        data: list[str] = []
        for line in frame.split("\n"):
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data.append(line[6:])
        events.append((name, "\n".join(data)))
    return events


# --- Date-scoped summaries --------------------------------------------------


def test_a_scoped_context_holds_only_the_entries_in_range(client: TestClient) -> None:
    signup(client, "scoped@example.com", "Scoped")
    opportunity = create_opportunity(client, "Long running")
    entry(client, opportunity["id"], "January call", "2026-01-15T10:00:00")
    entry(client, opportunity["id"], "June call", "2026-06-15T10:00:00")
    entry(client, opportunity["id"], "October call", "2026-10-15T10:00:00")

    with db_connection() as connection:
        context, numbers = ai_service.build_timeline_context(
            connection, opportunity["id"], since="2026-05-01", until="2026-07-01"
        )

    assert "June call" in context
    assert "January call" not in context
    assert "October call" not in context
    # The number is the deal's own sequence, not a position in the window:
    # the June call is #2 on screen and #2 here, with #1 outside the range.
    listed = client.get(f"/api/v2/opportunities/{opportunity['id']}/timeline?limit=50").json()
    june = next(item for item in listed["items"] if item["title"] == "June call")
    assert numbers == [june["sequence"]]
    assert numbers != [1], "a window must not renumber from one"


def test_the_bounds_include_the_whole_of_their_own_day(client: TestClient) -> None:
    """ "Until the 14th" that excluded the 14th would be wrong in the way
    nobody checks until it has lost them something."""
    signup(client, "bounds@example.com", "Bounds")
    opportunity = create_opportunity(client, "Edges")
    entry(client, opportunity["id"], "Late on the last day", "2026-06-30T23:30:00")
    entry(client, opportunity["id"], "Early on the first day", "2026-06-01T00:10:00")

    with db_connection() as connection:
        context, _ = ai_service.build_timeline_context(
            connection, opportunity["id"], since="2026-06-01", until="2026-06-30"
        )

    assert "Late on the last day" in context
    assert "Early on the first day" in context


def test_a_scoped_context_says_that_it_is_scoped(client: TestClient) -> None:
    """**D-185.** Without this the model reads a window as the whole deal and
    answers "pricing was never discussed" when the truth is "not in June"."""
    signup(client, "says@example.com", "Says")
    opportunity = create_opportunity(client, "Windowed")
    entry(client, opportunity["id"], "A call", "2026-06-15T10:00:00")

    with db_connection() as connection:
        scoped, _ = ai_service.build_timeline_context(
            connection, opportunity["id"], since="2026-06-01", until="2026-06-30"
        )
        whole, _ = ai_service.build_timeline_context(connection, opportunity["id"])

    assert "SCOPED to entries between 2026-06-01 and 2026-06-30" in scoped
    assert "not all of it" in scoped
    # An unscoped context is unchanged, byte for byte: every other context
    # test asserts on its exact shape.
    assert "SCOPED" not in whole


def test_each_half_of_the_range_reads_on_its_own(client: TestClient) -> None:
    signup(client, "halves@example.com", "Halves")
    opportunity = create_opportunity(client, "Open ended")
    entry(client, opportunity["id"], "A call", "2026-06-15T10:00:00")

    with db_connection() as connection:
        after, _ = ai_service.build_timeline_context(
            connection, opportunity["id"], since="2026-01-01"
        )
        before, _ = ai_service.build_timeline_context(
            connection, opportunity["id"], until="2026-12-31"
        )

    assert "from 2026-01-01 onwards" in after
    assert "up to 2026-12-31" in before


def test_the_route_passes_the_range_through(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    signup(client, "through@example.com", "Through")
    opportunity = create_opportunity(client, "Ranged")
    entry(client, opportunity["id"], "January call", "2026-01-15T10:00:00")
    entry(client, opportunity["id"], "June call", "2026-06-15T10:00:00")
    captured = stub_answer(monkeypatch, "An answer.")

    response = client.post(
        f"/api/v2/opportunities/{opportunity['id']}/ai/ask",
        json={"question": "What happened?", "since": "2026-05-01", "until": "2026-07-01"},
    )

    assert response.status_code == 200
    assert "June call" in captured["input"]
    assert "January call" not in captured["input"]


def test_a_range_that_ends_before_it_starts_is_refused(client: TestClient) -> None:
    signup(client, "backwards@example.com", "Backwards")
    opportunity = create_opportunity(client, "Backwards")

    response = client.post(
        f"/api/v2/opportunities/{opportunity['id']}/ai/ask",
        json={"question": "?", "since": "2026-07-01", "until": "2026-05-01"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["fields"]["_"] == "The range ends before it starts"


# --- Streaming --------------------------------------------------------------


def test_the_answer_arrives_in_pieces_and_ends_with_its_citations(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    signup(client, "stream@example.com", "Stream")
    opportunity = create_opportunity(client, "Streamed")
    entry(client, opportunity["id"], "Discovery call", "2026-06-15T10:00:00")
    captured = stub_stream(monkeypatch, ["The deal ", "is active. ", "See [Entry #2, today]."])

    with client.stream(
        "POST",
        f"/api/v2/opportunities/{opportunity['id']}/ai/ask/stream",
        json={"question": "How is it going?"},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = sse_events(b"".join(response.iter_bytes()).decode())

    assert captured["stream"] is True
    kinds = [name for name, _ in events]
    assert kinds == ["delta", "delta", "delta", "done"]
    assert [data for name, data in events if name == "delta"] == [
        "The deal ",
        "is active. ",
        "See [Entry #2, today].",
    ]
    done = json.loads(events[-1][1])
    assert done["answer"] == "The deal is active. See [Entry #2, today]."
    # Computed from the whole answer, which is why it cannot come any earlier.
    assert done["referenced_entry_numbers"] == [2]


def test_only_the_answer_reaches_the_reader(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reasoning model emits its thinking as events too. That is not the
    answer, and a reader watching it appear would be reading something this
    app never promised to show."""
    signup(client, "quiet@example.com", "Quiet")
    opportunity = create_opportunity(client, "Quiet stream")
    stub_stream(monkeypatch, ["Just the answer."])

    with client.stream(
        "POST",
        f"/api/v2/opportunities/{opportunity['id']}/ai/ask/stream",
        json={"question": "?"},
    ) as response:
        body = b"".join(response.iter_bytes()).decode()

    assert "thinking out loud" not in body


def test_an_answer_with_paragraphs_survives_its_own_framing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A newline inside a delta ends the SSE message unless every line gets
    its own `data:` prefix -- so a frame that forgot it would truncate every
    answer longer than one paragraph, silently."""
    signup(client, "para@example.com", "Para")
    opportunity = create_opportunity(client, "Paragraphs")
    stub_stream(monkeypatch, ["First paragraph.\n\nSecond paragraph."])

    with client.stream(
        "POST",
        f"/api/v2/opportunities/{opportunity['id']}/ai/ask/stream",
        json={"question": "?"},
    ) as response:
        events = sse_events(b"".join(response.iter_bytes()).decode())

    assert events[0] == ("delta", "First paragraph.\n\nSecond paragraph.")


def test_a_failure_mid_stream_is_an_event_rather_than_a_status(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The status line is long gone by the time the model fails, so a 502 is
    not available. The reader is told where the answer was going."""
    signup(client, "broke@example.com", "Broke")
    opportunity = create_opportunity(client, "Broken stream")

    class FakeResponses:
        def create(self, **kwargs: Any) -> Iterator[Any]:
            raise RuntimeError("upstream exploded")

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            self.responses = FakeResponses()

    monkeypatch.setattr("app.ai_service.OpenAI", FakeClient)

    with client.stream(
        "POST",
        f"/api/v2/opportunities/{opportunity['id']}/ai/ask/stream",
        json={"question": "?"},
    ) as response:
        assert response.status_code == 200
        events = sse_events(b"".join(response.iter_bytes()).decode())

    # The sentence names the failure class since R.1 (D-192); what this test is
    # about is that it arrives as an event rather than as a status.
    assert events == [("error", "The AI service is unavailable.")]


def test_a_reader_with_no_access_is_refused_before_the_stream_opens(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Checked before the response starts, so this is an ordinary 404 rather
    than a 200 whose first frame is bad news."""
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client, "Private")
    logout(client)
    signup(client, "outsider@example.com", "Outsider")
    stub_stream(monkeypatch, ["should not be sent"])

    response = client.post(
        f"/api/v2/opportunities/{opportunity['id']}/ai/ask/stream",
        json={"question": "?"},
    )

    assert response.status_code == 404


def test_a_viewer_may_stream_an_answer(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """The same rule the non-streaming ask has: asking a question is a read."""
    signup(client, "reader@example.com", "Reader")
    logout(client)
    signup(client, "holder@example.com", "Holder")
    opportunity = create_opportunity(client, "Shared")
    share(client, opportunity["id"], "reader@example.com", "viewer")
    logout(client)

    login(client, "reader@example.com")
    stub_stream(monkeypatch, ["An answer."])
    response = client.post(
        f"/api/v2/opportunities/{opportunity['id']}/ai/ask/stream",
        json={"question": "?"},
    )

    assert response.status_code == 200


# --- The filter proposal ----------------------------------------------------


def test_the_example_from_the_specification(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§14's own sentence: *"deals stuck in negotiation over 50k"*."""
    signup(client, "manager@example.com", "Manager")
    stub_answer(
        monkeypatch,
        json.dumps({"stage": "Negotiation", "min_value": 50000, "stalled": True}),
    )

    response = client.post(
        "/api/v2/ai/filter",
        json={"request": "deals stuck in negotiation over 50k"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["proposal"]["stage"] == "Negotiation"
    assert body["proposal"]["min_value"] == "50000"
    assert body["proposal"]["stalled"] is True
    assert body["ignored"] == []
    assert body["empty"] is False


def test_no_deal_content_is_sent_for_a_question_about_a_list(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    signup(client, "private@example.com", "Private")
    opportunity = create_opportunity(client, "Confidential Acme merger")
    entry(client, opportunity["id"], "Secret pricing discussion", "2026-06-15T10:00:00")
    captured = stub_answer(monkeypatch, "{}")

    client.post("/api/v2/ai/filter", json={"request": "big deals"})

    sent = f"{captured['instructions']}\n{captured['input']}"
    assert "Confidential Acme merger" not in sent
    assert "Secret pricing discussion" not in sent


def test_the_proposal_is_what_the_board_can_actually_do(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**D-186.** The inspection only means something if what is shown is
    what would be applied, so a stage this app does not have, a sort field it
    cannot sort by and a key it has never heard of are dropped -- and named,
    because a proposal that quietly discards half a request is one somebody
    accepts believing it did more."""
    signup(client, "strict@example.com", "Strict")
    stub_answer(
        monkeypatch,
        json.dumps(
            {
                "stage": "Haggling",
                "sort": "profitability",
                "owner": "Alex",
                "min_value": "lots",
                "q": "acme",
            }
        ),
    )

    body = client.post("/api/v2/ai/filter", json={"request": "anything"}).json()

    assert body["proposal"]["q"] == "acme"
    assert body["proposal"]["stage"] is None
    assert body["proposal"]["sort"] is None
    assert body["ignored"] == ["min_value", "owner", "sort", "stage"]
    assert body["empty"] is False


def test_nothing_understood_says_so_rather_than_offering_an_empty_filter(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    signup(client, "nothing@example.com", "Nothing")
    stub_answer(monkeypatch, "{}")

    body = client.post("/api/v2/ai/filter", json={"request": "hello"}).json()

    assert body["empty"] is True
    assert body["proposal"]["q"] is None


def test_an_answer_that_is_not_json_is_a_proposal_of_nothing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    signup(client, "prose@example.com", "Prose")
    stub_answer(monkeypatch, "I think you probably want the big deals.")

    body = client.post("/api/v2/ai/filter", json={"request": "big ones"}).json()

    assert body["empty"] is True
    assert body["ignored"] == ["the answer was not JSON"]


def test_a_fenced_answer_is_read_rather_than_refused() -> None:
    """The prompt says JSON only and a model will wrap it anyway. This is the
    single most common way the call fails, and refusing it would tell a
    person their request was not understood when it was understood and
    dressed up."""
    parsed = ai_filters.parse_filter_answer('```json\n{"stage": "Proposal"}\n```')

    assert parsed.proposal.stage == "Proposal"
    assert parsed.ignored == []


def test_a_sort_direction_with_nothing_to_sort_is_dropped() -> None:
    parsed = ai_filters.parse_filter_answer(json.dumps({"direction": "desc"}))

    assert parsed.proposal.direction is None
    assert parsed.ignored == ["direction"]
    assert parsed.empty is True


def test_free_text_is_flattened_and_bounded() -> None:
    """A newline in a filter chip breaks the row it sits in, and a thousand
    characters of it is not a search term."""
    parsed = ai_filters.parse_filter_answer(json.dumps({"q": "acme\n\n  corporation"}))
    long = ai_filters.parse_filter_answer(json.dumps({"q": "x" * 500}))

    assert parsed.proposal.q == "acme corporation"
    assert len(long.proposal.q or "") == ai_filters.MAX_TEXT


def test_a_filter_this_board_does_not_have_is_named_rather_than_invented() -> None:
    """The correction this milestone made to itself: an earlier draft
    proposed `owner` and a close-date range, which the filter bar does not
    offer -- an inspectable proposal that could not be applied. Being told
    "I could not express the owner" is useful; a chip that does nothing is
    not."""
    parsed = ai_filters.parse_filter_answer(
        json.dumps({"stage": "Proposal", "owner": "Alex", "closing_before": "2026-12-31"})
    )

    assert parsed.proposal.stage == "Proposal"
    assert parsed.ignored == ["closing_before", "owner"]
    assert parsed.empty is False


def test_numbers_arrive_in_the_shapes_a_model_actually_sends() -> None:
    for raw, expected in (
        (50000, "50000"),
        (50000.0, "50000"),
        ("50000", "50000"),
        ("50000.50", "50000.5"),
    ):
        parsed = ai_filters.parse_filter_answer(json.dumps({"min_value": raw}))
        assert parsed.proposal.min_value == expected, raw

    for bad in ("50k", True, None, -5):
        parsed = ai_filters.parse_filter_answer(json.dumps({"min_value": bad}))
        assert parsed.proposal.min_value is None, bad


def test_the_filter_endpoint_needs_a_key_and_a_session(client: TestClient) -> None:
    assert client.post("/api/v2/ai/filter", json={"request": "x"}).status_code == 401

    signup(client, "keyless@example.com", "Keyless")
    settings.openai_api_key = None
    try:
        assert client.post("/api/v2/ai/filter", json={"request": "x"}).status_code == 503
    finally:
        settings.openai_api_key = "test-key"


def test_what_the_model_could_not_express_is_reported_too() -> None:
    """The gap found by asking the running system rather than a stub: *"Gavin
    deals closing before December in EMEA"* came back with a search term and
    `ignored: []`, because `ignored` only names keys the model **sent** that
    this dropped. A model that obeys the prompt and omits what it cannot
    express reports nothing at all -- so it is now asked to say, in the
    person's own words."""
    parsed = ai_filters.parse_filter_answer(
        json.dumps(
            {
                "q": "Gavin",
                "unused": ["closing before December", "in EMEA"],
            }
        )
    )

    assert parsed.proposal.q == "Gavin"
    assert parsed.ignored == ["closing before December", "in EMEA"]
    assert parsed.empty is False


def test_the_unused_list_is_bounded_and_flattened() -> None:
    """It is shown on screen, so a newline would break the row it sits in and
    an unbounded list would be a paragraph where a note belongs."""
    parsed = ai_filters.parse_filter_answer(
        json.dumps(
            {
                "stage": "Proposal",
                "unused": [
                    "a\n\nmultiline phrase",
                    "x" * 400,
                    *[f"phrase {index}" for index in range(10)],
                    42,
                    "",
                ],
            }
        )
    )

    assert "a multiline phrase" in parsed.ignored
    assert all(len(phrase) <= ai_filters.MAX_TEXT for phrase in parsed.ignored)
    assert len(parsed.ignored) <= ai_filters.MAX_UNUSED


def test_unused_is_not_mistaken_for_a_filter() -> None:
    """It is a report, not a key the board has -- so it must not end up in
    `ignored` as an unknown key, which is what would happen if it were left
    in the payload for the loop to find."""
    parsed = ai_filters.parse_filter_answer(json.dumps({"stage": "Proposal", "unused": []}))

    assert parsed.ignored == []
    assert parsed.empty is False
