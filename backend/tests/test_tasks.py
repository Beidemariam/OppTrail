"""Tasks scoped to an opportunity (milestone 4.1, `docs/FEATURES.md` §8).

The authorization matrix already covers who may call each route; this file is
about what the routes *do*. Four properties carry the milestone:

- completing is open to the assignee and editing is not (**D-142**),
- the done state is a timestamp and a pair of idempotent routes, not a field,
- My Tasks spans opportunities and is filtered by access inside the query,
- a task is content, so deleting one is soft, audited and undoable.
"""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.database import db_connection


def days_from_now(days: int) -> str:
    """A date relative to today, so no assertion depends on the wall clock."""
    return (datetime.now(UTC) + timedelta(days=days)).date().isoformat()


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


def logout(client: TestClient) -> None:
    assert client.post("/api/v2/auth/logout").status_code == 200


def create_opportunity(client: TestClient, name: str = "Expansion") -> dict:
    response = client.post(
        "/api/v2/opportunities",
        json={
            "name": name,
            "account_name": "Acme",
            "value": "25000",
            "currency": "USD",
            "stage": "Prospecting",
            "expected_close_date": "2026-10-15",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_task(client: TestClient, opportunity_id: int, **fields) -> dict:
    payload = {"title": "Call them back"} | fields
    response = client.post(f"/api/v2/opportunities/{opportunity_id}/tasks", json=payload)
    assert response.status_code == 201, response.json()
    return response.json()


def test_a_task_carries_its_deal_its_assignee_and_its_due_date(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)

    task = create_task(
        client,
        opportunity["id"],
        title="  Send the revised pricing  ",
        due_date=days_from_now(3),
    )

    assert task["title"] == "Send the revised pricing"
    assert task["opportunity_name"] == "Expansion"
    assert task["completed_at"] is None
    assert task["assignees"] == []
    assert task["due_date"] == days_from_now(3)


def test_a_blank_title_is_refused(client: TestClient) -> None:
    """`Field(min_length=1)` runs before the strip, so whitespace satisfied it
    and was stored as an empty title until `schemas.stripped` closed the hole.
    The same defect was live on an opportunity's name and account name."""
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)

    response = client.post(
        f"/api/v2/opportunities/{opportunity['id']}/tasks", json={"title": "   "}
    )

    assert response.status_code == 422


def test_an_assignee_is_named_by_email_and_told(client: TestClient) -> None:
    colleague = signup(client, "gavin@example.com", "Gavin")
    logout(client)
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)

    task = create_task(client, opportunity["id"], assignee_emails=["GAVIN@example.com"])

    assert [item["user_id"] for item in task["assignees"]] == [colleague["id"]]
    assert [item["name"] for item in task["assignees"]] == ["Gavin"]

    logout(client)
    login(client, "gavin@example.com")
    notifications = client.get("/api/v2/notifications?type=task_assigned").json()["items"]
    assert len(notifications) == 1
    # The title rides along so the inbox can name the task without a second read.
    assert notifications[0]["payload"]["title"] == "Call them back"
    assert notifications[0]["payload"]["task_id"] == task["id"]


def test_assigning_a_task_to_yourself_notifies_nobody(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)

    create_task(client, opportunity["id"], assignee_emails=["owner@example.com"])

    assert client.get("/api/v2/notifications?type=task_assigned").json()["items"] == []


def test_an_unknown_assignee_is_refused_before_anything_is_written(
    client: TestClient,
) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)

    response = client.post(
        f"/api/v2/opportunities/{opportunity['id']}/tasks",
        json={"title": "Call back", "assignee_emails": ["nobody@example.com"]},
    )

    assert response.status_code == 422
    assert "nobody@example.com" in response.json()["error"]["message"]
    assert client.get(f"/api/v2/opportunities/{opportunity['id']}/tasks").json()["items"] == []


def test_a_linked_entry_must_belong_to_the_same_opportunity(client: TestClient) -> None:
    """The rule a reply's parent follows (D-127), for the same reason: a foreign
    key cannot express it, so the route does."""
    signup(client, "owner@example.com", "Owner")
    first = create_opportunity(client, "First")
    second = create_opportunity(client, "Second")
    entry = client.post(
        f"/api/v2/opportunities/{second['id']}/timeline",
        json={
            "type": "call",
            "title": "Discovery",
            "body": "Body",
            "event_timestamp": "2026-09-01T10:00",
        },
    ).json()

    response = client.post(
        f"/api/v2/opportunities/{first['id']}/tasks",
        json={"title": "Follow up", "entry_id": entry["id"]},
    )

    assert response.status_code == 404


def test_a_task_outlives_the_entry_that_prompted_it(client: TestClient) -> None:
    """Deleting the entry does not delete the action item it produced: the task
    is scoped to the deal and merely links to the entry, so it keeps its own
    `entry_id` and simply stops naming a title."""
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    entry = client.post(
        f"/api/v2/opportunities/{opportunity['id']}/timeline",
        json={
            "type": "call",
            "title": "Discovery",
            "body": "Body",
            "event_timestamp": "2026-09-01T10:00",
        },
    ).json()
    task = create_task(client, opportunity["id"], entry_id=entry["id"])
    assert task["entry_title"] == "Discovery"

    assert client.delete(f"/api/v2/timeline/{entry['id']}").status_code == 204

    tasks = client.get(f"/api/v2/opportunities/{opportunity['id']}/tasks").json()["items"]
    assert len(tasks) == 1
    assert tasks[0]["entry_id"] == entry["id"]
    assert tasks[0]["entry_title"] is None


def share(client: TestClient, opportunity_id: int, email: str, role: str) -> None:
    assert (
        client.post(
            f"/api/v2/opportunities/{opportunity_id}/shares",
            json={"email": email, "role": role},
        ).status_code
        == 201
    )


def test_the_assignee_can_complete_a_task_they_did_not_write(client: TestClient) -> None:
    """**D-142.** Handing somebody a task and then refusing to let them close it
    is not a permission model. The assignee here is an editor and the author is
    the owner, so the ordinary author-or-owner rule (D-005) would refuse them."""
    signup(client, "gavin@example.com", "Gavin")
    logout(client)
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    share(client, opportunity["id"], "gavin@example.com", "editor")
    task = create_task(client, opportunity["id"], assignee_emails=["gavin@example.com"])
    logout(client)

    login(client, "gavin@example.com")
    completed = client.post(f"/api/v2/tasks/{task['id']}/complete")

    assert completed.status_code == 200
    assert completed.json()["completed_at"] is not None
    assert completed.json()["completed_by_name"] == "Gavin"

    # ...and editing it is still refused, which is the line the decision draws.
    assert client.patch(f"/api/v2/tasks/{task['id']}", json={"title": "Renamed"}).status_code == 403


def test_an_editor_who_is_not_the_assignee_cannot_complete_it(client: TestClient) -> None:
    signup(client, "gavin@example.com", "Gavin")
    logout(client)
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    share(client, opportunity["id"], "gavin@example.com", "editor")
    # Assigned to nobody, so the editor has no claim on it beyond being an editor.
    task = create_task(client, opportunity["id"])
    logout(client)

    login(client, "gavin@example.com")

    assert client.post(f"/api/v2/tasks/{task['id']}/complete").status_code == 403


def test_completing_twice_keeps_the_first_completion(client: TestClient) -> None:
    """Idempotent through `COALESCE`, so the first completer is the one recorded
    and a double click is not a second event -- the shape resolve uses (3.3)."""
    signup(client, "gavin@example.com", "Gavin")
    logout(client)
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    share(client, opportunity["id"], "gavin@example.com", "editor")
    task = create_task(client, opportunity["id"], assignee_emails=["gavin@example.com"])
    logout(client)

    login(client, "gavin@example.com")
    first = client.post(f"/api/v2/tasks/{task['id']}/complete").json()
    logout(client)

    login(client, "owner@example.com")
    second = client.post(f"/api/v2/tasks/{task['id']}/complete").json()

    assert second["completed_at"] == first["completed_at"]
    assert second["completed_by"] == first["completed_by"]


def test_reopening_puts_it_back_on_the_list(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    task = create_task(client, opportunity["id"])

    client.post(f"/api/v2/tasks/{task['id']}/complete")
    reopened = client.post(f"/api/v2/tasks/{task['id']}/reopen")

    assert reopened.status_code == 200
    assert reopened.json()["completed_at"] is None
    assert reopened.json()["completed_by"] is None
    # Reopening an open task is a no-op rather than an error, so a client that
    # lost track of the state cannot get stuck.
    assert client.post(f"/api/v2/tasks/{task['id']}/reopen").status_code == 200


def test_a_partial_patch_clears_a_date_and_leaves_the_rest(client: TestClient) -> None:
    """`null` clears, an absent key leaves alone -- two different things, told
    apart by `model_fields_set` rather than by the value."""
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    task = create_task(client, opportunity["id"], title="Original", due_date=days_from_now(5))

    patched = client.patch(f"/api/v2/tasks/{task['id']}", json={"due_date": None})

    assert patched.status_code == 200
    assert patched.json()["due_date"] is None
    assert patched.json()["title"] == "Original"

    untouched = client.patch(f"/api/v2/tasks/{task['id']}", json={"title": "Renamed"})
    assert untouched.json()["title"] == "Renamed"
    assert untouched.json()["due_date"] is None


def test_the_list_puts_undated_tasks_last(client: TestClient) -> None:
    """SQLite sorts `NULL` before every value, so without `due_date IS NULL` as
    the first sort key a task with no date would lead the list."""
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    create_task(client, opportunity["id"], title="No date")
    create_task(client, opportunity["id"], title="Later", due_date=days_from_now(9))
    create_task(client, opportunity["id"], title="Sooner", due_date=days_from_now(2))

    titles = [
        task["title"]
        for task in client.get(f"/api/v2/opportunities/{opportunity['id']}/tasks").json()["items"]
    ]

    assert titles == ["Sooner", "Later", "No date"]


def test_my_tasks_spans_opportunities_and_hides_the_ones_you_cannot_see(
    client: TestClient,
) -> None:
    """The permission filter is inside the query, like search's. A task can be
    assigned to somebody before they are shared on the deal, so removing the
    share has to take the task off their list rather than leak the deal's name
    through it."""
    signup(client, "gavin@example.com", "Gavin")
    logout(client)
    signup(client, "owner@example.com", "Owner")
    shared = create_opportunity(client, "Shared deal")
    private = create_opportunity(client, "Private deal")
    share(client, shared["id"], "gavin@example.com", "editor")
    create_task(
        client, shared["id"], title="On the shared deal", assignee_emails=["gavin@example.com"]
    )
    create_task(
        client, private["id"], title="On the private deal", assignee_emails=["gavin@example.com"]
    )
    logout(client)

    login(client, "gavin@example.com")
    mine = client.get("/api/v2/tasks").json()["items"]

    assert [task["title"] for task in mine] == ["On the shared deal"]
    assert mine[0]["opportunity_name"] == "Shared deal"


def test_my_tasks_shows_open_work_by_default(client: TestClient) -> None:
    """A list of everything you have ever finished is not a to-do list."""
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    done = create_task(
        client, opportunity["id"], title="Done", assignee_emails=["owner@example.com"]
    )
    create_task(client, opportunity["id"], title="Open", assignee_emails=["owner@example.com"])
    client.post(f"/api/v2/tasks/{done['id']}/complete")

    assert [t["title"] for t in client.get("/api/v2/tasks").json()["items"]] == ["Open"]
    both = client.get("/api/v2/tasks?include_completed=true").json()["items"]
    assert sorted(t["title"] for t in both) == ["Done", "Open"]


def test_overdue_is_a_date_filter_and_skips_the_undated(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    create_task(
        client,
        opportunity["id"],
        title="Overdue",
        assignee_emails=["owner@example.com"],
        due_date=days_from_now(-2),
    )
    create_task(
        client,
        opportunity["id"],
        title="Later",
        assignee_emails=["owner@example.com"],
        due_date=days_from_now(4),
    )
    create_task(client, opportunity["id"], title="No date", assignee_emails=["owner@example.com"])

    overdue = client.get(f"/api/v2/tasks?due_before={days_from_now(0)}").json()["items"]

    assert [task["title"] for task in overdue] == ["Overdue"]


def test_deleting_a_task_is_soft_audited_and_undoable(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    task = create_task(client, opportunity["id"], title="Send pricing")

    assert client.delete(f"/api/v2/tasks/{task['id']}").status_code == 204
    assert client.get(f"/api/v2/opportunities/{opportunity['id']}/tasks").json()["items"] == []

    audit = client.get(f"/api/v2/opportunities/{opportunity['id']}/audit-log").json()["items"]
    deleted = [row for row in audit if row["action"] == "task_deleted"]
    assert len(deleted) == 1
    assert deleted[0]["detail"]["title"] == "Send pricing"

    assert client.post(f"/api/v2/tasks/{task['id']}/restore").status_code == 204
    restored = client.get(f"/api/v2/opportunities/{opportunity['id']}/tasks").json()["items"]
    assert [row["title"] for row in restored] == ["Send pricing"]

    # Undo writes its own row rather than removing the delete's: the log is the
    # sequence of what happened (milestone 2.4b).
    audit = client.get(f"/api/v2/opportunities/{opportunity['id']}/audit-log").json()["items"]
    assert [row["action"] for row in audit if row["action"].startswith("task_")] == [
        "task_deleted",
        "task_restored",
    ]


def test_restoring_a_live_task_is_a_404(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    task = create_task(client, opportunity["id"])

    assert client.post(f"/api/v2/tasks/{task['id']}/restore").status_code == 404


def test_deleting_an_opportunity_stamps_its_tasks_too(client: TestClient) -> None:
    """Tasks are a level of the delete cascade.

    Asserted against the row's own `deleted_at` rather than through My Tasks,
    because My Tasks filters deleted opportunities *as well* and therefore
    cannot tell a stamped task from an unstamped one -- the first version of
    this test passed with the cascade removed, which is what the project's
    fail-it-first rule exists to catch. What the cascade is for is the row
    itself: an unstamped task under a deleted deal is a live row whose parent
    is gone, and restoring the opportunity would then be unable to tell which
    tasks its own delete took.
    """
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    task = create_task(client, opportunity["id"], assignee_emails=["owner@example.com"])

    assert client.delete(f"/api/v2/opportunities/{opportunity['id']}").status_code == 204

    with db_connection() as connection:
        stamp = connection.execute(
            "SELECT deleted_at FROM tasks WHERE id = ?", (task["id"],)
        ).fetchone()["deleted_at"]
    assert stamp is not None

    # One cascade writes one stamp across everything it takes, so Undo asks for
    # that value back and the task returns with the rest of the deal.
    assert client.post(f"/api/v2/opportunities/{opportunity['id']}/restore").status_code == 204
    with db_connection() as connection:
        assert (
            connection.execute(
                "SELECT deleted_at FROM tasks WHERE id = ?", (task["id"],)
            ).fetchone()["deleted_at"]
            is None
        )
    assert len(client.get("/api/v2/tasks").json()["items"]) == 1


def test_the_calendar_reads_every_visible_task_in_a_date_range(client: TestClient) -> None:
    """`assignee=any` with `from`/`to` is the calendar's follow-up layer
    (milestone 4.2), replacing the `follow_up_date` read D-088 added.

    It must show a colleague's task, which is the difference from My Tasks, and
    must still stop at the edge of what the reader may see.
    """
    signup(client, "gavin@example.com", "Gavin")
    logout(client)
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    share(client, opportunity["id"], "gavin@example.com", "editor")
    create_task(
        client,
        opportunity["id"],
        title="Gavin's task",
        assignee_emails=["gavin@example.com"],
        due_date=days_from_now(4),
    )
    create_task(
        client,
        opportunity["id"],
        title="Mine, this month",
        assignee_emails=["owner@example.com"],
        due_date=days_from_now(6),
    )
    create_task(client, opportunity["id"], title="Far future", due_date=days_from_now(90))
    create_task(client, opportunity["id"], title="No date at all")

    window = f"from={days_from_now(0)}&to={days_from_now(30)}"
    items = client.get(f"/api/v2/tasks?assignee=any&{window}").json()["items"]

    # Somebody else's task is in, an out-of-range one is out, and an undated one
    # cannot be placed on a grid of days at all.
    assert sorted(task["title"] for task in items) == [
        "Gavin's task",
        "Mine, this month",
    ]

    # ...and the default is still My Tasks, which is the other reader. Only the
    # one actually assigned to this reader: a task written down and handed to
    # nobody belongs to the deal, not to its author's to-do list, which is why
    # the composer's assignee choice includes "Nobody yet".
    mine = client.get(f"/api/v2/tasks?{window}").json()["items"]
    assert [task["title"] for task in mine] == ["Mine, this month"]


def test_a_task_on_a_deal_you_cannot_see_stays_invisible_to_the_calendar(
    client: TestClient,
) -> None:
    signup(client, "gavin@example.com", "Gavin")
    logout(client)
    signup(client, "owner@example.com", "Owner")
    private = create_opportunity(client, "Private")
    create_task(client, private["id"], title="Secret task", due_date=days_from_now(3))
    logout(client)

    login(client, "gavin@example.com")
    window = f"from={days_from_now(0)}&to={days_from_now(30)}"

    assert client.get(f"/api/v2/tasks?assignee=any&{window}").json()["items"] == []


def test_a_task_due_far_in_the_future_is_still_in_its_own_month(client: TestClient) -> None:
    """The calendar asks for one month at a time, and the month it draws may be
    years away — `?opportunities.month=2027-08` is a legitimate URL. A window
    that only ever covers the near future would silently draw an empty grid."""
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    create_task(
        client,
        opportunity["id"],
        title="Send updated pricing",
        assignee_emails=["owner@example.com"],
        due_date="2027-08-19",
    )

    items = client.get("/api/v2/tasks?assignee=any&from=2027-07-26&to=2027-09-05").json()["items"]

    assert [task["title"] for task in items] == ["Send updated pricing"]


def test_an_edit_to_a_task_is_recoverable_and_reaches_the_activity_log(
    client: TestClient,
) -> None:
    """`AGENTS.md` invariant 8 for tasks (milestone 4.2a).

    Milestone 4.1 shipped an editable task with no history, which is the
    violation the human found at the Phase 4 checkpoint -- and asked for by name:
    "it is also good to have the history of the task captured in the activity
    log." Both halves are here: the history itself, and the one feed that reads
    it.
    """
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    task = create_task(client, opportunity["id"], title="Call them back", due_date=days_from_now(4))

    # Version 1 is written at creation, so the history opens with what the task
    # said on day one rather than with its first edit (D-097's rule).
    versions = client.get(f"/api/v2/tasks/{task['id']}/versions").json()["items"]
    assert [v["version_number"] for v in versions] == [1]
    assert versions[0]["title"] == "Call them back"

    client.patch(
        f"/api/v2/tasks/{task['id']}",
        json={"title": "Call them today", "description": "They asked for pricing."},
    )

    versions = client.get(f"/api/v2/tasks/{task['id']}/versions").json()["items"]
    assert [v["version_number"] for v in versions] == [1, 2]
    # The whole state, every time, so no reader reconstructs one from a chain.
    assert versions[1]["title"] == "Call them today"
    assert versions[1]["description"] == "They asked for pricing."
    assert versions[1]["due_date"] == days_from_now(4)
    # The earlier value is still readable, which is what "recoverable" means.
    assert versions[0]["title"] == "Call them back"
    assert versions[0]["description"] == ""

    # ...and the edit is in the one place that answers "who did what when".
    feed = client.get(f"/api/v2/opportunities/{opportunity['id']}/activity").json()["items"]
    task_edits = [event for event in feed if event["detail"].get("target") == "task"]
    assert len(task_edits) == 1
    assert task_edits[0]["detail"]["version_number"] == 2


def test_ticking_a_task_off_writes_no_version(client: TestClient) -> None:
    """`completed_at` is deliberately not a versioned field: checking a task and
    unchecking it is toggle state a person sets and unsets, not content quietly
    rewritten, so a history of every check is a log nobody reads (D-130's
    reasoning applied to invariant 8's scope)."""
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    task = create_task(client, opportunity["id"])

    client.post(f"/api/v2/tasks/{task['id']}/complete")
    client.post(f"/api/v2/tasks/{task['id']}/reopen")

    versions = client.get(f"/api/v2/tasks/{task['id']}/versions").json()["items"]
    assert [v["version_number"] for v in versions] == [1]


def test_a_task_carries_a_description(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)

    task = create_task(
        client,
        opportunity["id"],
        title="Send pricing",
        description="They want the **2027** figures.",
    )

    assert task["description"] == "They want the **2027** figures."
    # Empty rather than null when nobody wrote one, so every reader treats it as
    # a string and the composer has nothing to special-case.
    plain = create_task(client, opportunity["id"], title="No detail")
    assert plain["description"] == ""


def test_a_task_edit_can_be_put_back(client: TestClient) -> None:
    """The fourth restorable history (milestone 4.2a, D-116/D-120): the restore is
    itself recorded, so it can be undone in turn and nothing is lost."""
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    task = create_task(client, opportunity["id"], title="Call them back")
    client.patch(f"/api/v2/tasks/{task['id']}", json={"title": "Call them today"})

    restored = client.post(f"/api/v2/tasks/{task['id']}/versions/1/restore")

    assert restored.status_code == 200
    assert restored.json()["title"] == "Call them back"
    # Version 3, not a rewind to 1: the history only grows, so the edit this
    # restore replaced is itself recoverable.
    versions = client.get(f"/api/v2/tasks/{task['id']}/versions").json()["items"]
    assert [v["version_number"] for v in versions] == [1, 2, 3]
    assert versions[2]["title"] == "Call them back"

    # Restoring what is already current writes nothing, which is what makes a
    # retry safe (the server's half of D-114).
    assert client.post(f"/api/v2/tasks/{task['id']}/versions/3/restore").status_code == 200
    versions = client.get(f"/api/v2/tasks/{task['id']}/versions").json()["items"]
    assert len(versions) == 3


# --- A task's discussion (milestone 4.5, D-162) ----------------------------


def comment_on(client: TestClient, task_id: int, body: str) -> dict:
    response = client.post(f"/api/v2/tasks/{task_id}/comments", json={"body": body})
    assert response.status_code == 201, response.json()
    return response.json()


def test_a_task_carries_the_discussion_it_provokes(client: TestClient) -> None:
    """Read with the task rather than through a list route of its own, the way
    a note's comments are -- and chronological, because a log is."""
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    # Assigned to the writer, because My Tasks below answers with the caller's
    # own assignments and an unassigned task is on nobody's list.
    task = create_task(client, opportunity["id"], assignee_emails=["owner@example.com"])

    comment_on(client, task["id"], "  Chased them, no answer  ")
    comment_on(client, task["id"], "Moved to Thursday")

    tasks = client.get(f"/api/v2/opportunities/{opportunity['id']}/tasks").json()["items"]
    discussion = next(item for item in tasks if item["id"] == task["id"])["comments"]
    assert [item["body"] for item in discussion] == [
        "Chased them, no answer",
        "Moved to Thursday",
    ]
    assert discussion[0]["author_name"] == "Owner"
    # My Tasks reads the same shape, so a discussion is not a reason to open
    # the deal.
    mine = client.get("/api/v2/tasks").json()["items"]
    assert len(next(item for item in mine if item["id"] == task["id"])["comments"]) == 2


def test_a_viewer_reads_the_discussion_and_cannot_add_to_it(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    signup(client, "viewer@example.com", "Viewer")
    login(client, "owner@example.com")
    opportunity = create_opportunity(client)
    task = create_task(client, opportunity["id"])
    comment_on(client, task["id"], "Chased them")
    share(client, opportunity["id"], "viewer@example.com", "viewer")
    logout(client)
    login(client, "viewer@example.com")

    readable = client.get(f"/api/v2/opportunities/{opportunity['id']}/tasks").json()["items"]
    refused = client.post(f"/api/v2/tasks/{task['id']}/comments", json={"body": "Mine"})

    assert len(readable[0]["comments"]) == 1
    assert refused.status_code == 403


def test_a_comment_tells_everyone_the_task_is_about(client: TestClient) -> None:
    """The task's author and **everyone** it is assigned to, as a set -- so
    somebody who is both is told once -- and never the person who wrote the
    comment.

    Both directions are asserted on purpose. The earlier version of this test
    only checked that the author hears and the author-assignee does not, which
    passed happily when milestone 4.6 left this read on `tasks.assignee_id` --
    a column 4.6 stopped writing. An assignee who is not the author is the case
    that caught it, and only the end-to-end run did.
    """
    signup(client, "owner@example.com", "Owner")
    signup(client, "gavin@example.com", "Gavin")
    signup(client, "max@example.com", "Maximilian")
    login(client, "owner@example.com")
    opportunity = create_opportunity(client)
    share(client, opportunity["id"], "gavin@example.com", "editor")
    share(client, opportunity["id"], "max@example.com", "editor")
    task = create_task(
        client,
        opportunity["id"],
        assignee_emails=["gavin@example.com", "max@example.com"],
    )
    logout(client)

    login(client, "gavin@example.com")
    comment_on(client, task["id"], "Left a voicemail")
    gavin_inbox = client.get("/api/v2/notifications?type=task_comment").json()["items"]
    logout(client)

    # Gavin wrote the comment and is an assignee: no notification to himself.
    assert gavin_inbox == []
    # The author hears, and so does the other assignee.
    for email in ("owner@example.com", "max@example.com"):
        login(client, email)
        inbox = client.get("/api/v2/notifications?type=task_comment").json()["items"]
        logout(client)
        assert [item["payload"]["title"] for item in inbox] == ["Call them back"], email


def test_a_comment_is_immutable(client: TestClient) -> None:
    """`AGENTS.md` invariant 2, read against the second kind of comment: there
    is no edit route, so removing it is the only change it can undergo."""
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    task = create_task(client, opportunity["id"])
    comment = comment_on(client, task["id"], "Chased them")

    assert client.patch(
        f"/api/v2/task-comments/{comment['id']}", json={"body": "No"}
    ).status_code in (
        404,
        405,
    )


def test_deleting_a_comment_is_soft_audited_and_undoable(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    task = create_task(client, opportunity["id"])
    comment = comment_on(client, task["id"], "Chased them")

    assert client.delete(f"/api/v2/task-comments/{comment['id']}").status_code == 204
    assert task_comments(client, opportunity["id"], task["id"]) == []

    assert client.post(f"/api/v2/task-comments/{comment['id']}/restore").status_code == 204
    assert task_comments(client, opportunity["id"], task["id"]) == ["Chased them"]

    actions = [
        item["action"]
        for item in client.get(f"/api/v2/opportunities/{opportunity['id']}/audit-log").json()[
            "items"
        ]
    ]
    assert actions == ["task_comment_deleted", "task_comment_restored"]


def task_comments(client: TestClient, opportunity_id: int, task_id: int) -> list[str]:
    tasks = client.get(f"/api/v2/opportunities/{opportunity_id}/tasks").json()["items"]
    task = next(item for item in tasks if item["id"] == task_id)
    return [item["body"] for item in task["comments"]]


def test_the_discussion_is_a_level_of_the_task_cascade(client: TestClient) -> None:
    """A comment is readable only through its task, so it goes with the task
    and with the deal -- asserted against the row's own stamp, because every
    read filters the deleted parent anyway (4.1's first cascade test did not,
    and passed with the cascade removed)."""
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    task = create_task(client, opportunity["id"])
    comment = comment_on(client, task["id"], "Chased them")

    assert client.delete(f"/api/v2/tasks/{task['id']}").status_code == 204
    assert comment_deleted_at(comment["id"]) is not None

    assert client.post(f"/api/v2/tasks/{task['id']}/restore").status_code == 204
    assert comment_deleted_at(comment["id"]) is None

    assert client.delete(f"/api/v2/opportunities/{opportunity['id']}").status_code == 204
    assert comment_deleted_at(comment["id"]) is not None


def comment_deleted_at(comment_id: int) -> str | None:
    with db_connection() as connection:
        row = connection.execute(
            "SELECT deleted_at FROM task_comments WHERE id = ?",
            (comment_id,),
        ).fetchone()
    return row["deleted_at"]


def test_a_comment_deleted_on_its_own_stays_deleted_when_the_task_comes_back(
    client: TestClient,
) -> None:
    """One cascade writes one stamp, so a restore asks for that stamp back --
    the rule every other restore in this app follows."""
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)
    task = create_task(client, opportunity["id"])
    kept = comment_on(client, task["id"], "Chased them")
    removed = comment_on(client, task["id"], "Wrong task")

    assert client.delete(f"/api/v2/task-comments/{removed['id']}").status_code == 204
    # Backdated for the reason `test_restore.py`'s own helper backdates:
    # `utc_now()` has one-second resolution, so a delete made through the API
    # microseconds before the cascade would share its stamp and come back with
    # it -- the window D-067 accepts. This fixture means "deleted a while ago".
    with db_connection() as connection:
        connection.execute(
            "UPDATE task_comments SET deleted_at = datetime(deleted_at, '-1 hour') WHERE id = ?",
            (removed["id"],),
        )
        connection.commit()
    assert client.delete(f"/api/v2/tasks/{task['id']}").status_code == 204
    assert client.post(f"/api/v2/tasks/{task['id']}/restore").status_code == 204

    assert task_comments(client, opportunity["id"], task["id"]) == ["Chased them"]
    assert comment_deleted_at(kept["id"]) is None
    assert comment_deleted_at(removed["id"]) is not None


# --- More than one person on a task (milestone 4.6, D-146's other half) ----


def test_a_task_can_be_handed_to_several_people(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    gavin = signup(client, "gavin@example.com", "Gavin")
    max_ = signup(client, "max@example.com", "Maximilian")
    login(client, "owner@example.com")
    opportunity = create_opportunity(client)
    share(client, opportunity["id"], "gavin@example.com", "editor")
    share(client, opportunity["id"], "max@example.com", "editor")

    task = create_task(
        client,
        opportunity["id"],
        assignee_emails=["GAVIN@example.com", "max@example.com", "gavin@example.com"],
    )

    # Ascending by id, and the duplicate is one row rather than two.
    assert [item["user_id"] for item in task["assignees"]] == sorted([gavin["id"], max_["id"]])
    assert [item["name"] for item in task["assignees"]] == ["Gavin", "Maximilian"]


def test_each_new_assignee_is_told_once_and_the_assigner_never(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    signup(client, "gavin@example.com", "Gavin")
    signup(client, "max@example.com", "Maximilian")
    login(client, "owner@example.com")
    opportunity = create_opportunity(client)
    share(client, opportunity["id"], "gavin@example.com", "editor")
    share(client, opportunity["id"], "max@example.com", "editor")

    task = create_task(
        client,
        opportunity["id"],
        assignee_emails=["gavin@example.com", "owner@example.com"],
    )
    # Adding Maximilian leaves Gavin where he was: he is not told again.
    assert (
        client.patch(
            f"/api/v2/tasks/{task['id']}",
            json={"assignee_emails": ["gavin@example.com", "max@example.com"]},
        ).status_code
        == 200
    )
    logout(client)

    assert assignment_count(client, "owner@example.com") == 0
    assert assignment_count(client, "gavin@example.com") == 1
    assert assignment_count(client, "max@example.com") == 1


def assignment_count(client: TestClient, email: str) -> int:
    login(client, email)
    items = client.get("/api/v2/notifications?type=task_assigned").json()["items"]
    logout(client)
    return len(items)


def test_any_assignee_may_close_it_and_none_may_rewrite_it(client: TestClient) -> None:
    """**D-142** read against a set: a shared task is done when whoever got to
    it says so. Editing stays author-or-owner (D-005), which is the line that
    did not move."""
    signup(client, "owner@example.com", "Owner")
    signup(client, "gavin@example.com", "Gavin")
    signup(client, "max@example.com", "Maximilian")
    login(client, "owner@example.com")
    opportunity = create_opportunity(client)
    share(client, opportunity["id"], "gavin@example.com", "editor")
    share(client, opportunity["id"], "max@example.com", "editor")
    task = create_task(
        client,
        opportunity["id"],
        assignee_emails=["gavin@example.com", "max@example.com"],
    )
    logout(client)

    login(client, "max@example.com")
    completed = client.post(f"/api/v2/tasks/{task['id']}/complete")
    renamed = client.patch(f"/api/v2/tasks/{task['id']}", json={"title": "Mine now"})

    assert completed.status_code == 200
    assert completed.json()["completed_by_name"] == "Maximilian"
    assert renamed.status_code == 403


def test_my_tasks_answers_everyone_the_task_is_for(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    signup(client, "gavin@example.com", "Gavin")
    login(client, "owner@example.com")
    opportunity = create_opportunity(client)
    share(client, opportunity["id"], "gavin@example.com", "editor")
    create_task(
        client,
        opportunity["id"],
        title="Shared chase",
        assignee_emails=["owner@example.com", "gavin@example.com"],
    )
    create_task(
        client, opportunity["id"], title="Mine alone", assignee_emails=["owner@example.com"]
    )

    mine = [item["title"] for item in client.get("/api/v2/tasks").json()["items"]]
    logout(client)
    login(client, "gavin@example.com")
    theirs = [item["title"] for item in client.get("/api/v2/tasks").json()["items"]]

    assert sorted(mine) == ["Mine alone", "Shared chase"]
    assert theirs == ["Shared chase"]


def test_clearing_the_list_leaves_a_task_nobody_owes(client: TestClient) -> None:
    signup(client, "owner@example.com", "Owner")
    login(client, "owner@example.com")
    opportunity = create_opportunity(client)
    task = create_task(client, opportunity["id"], assignee_emails=["owner@example.com"])

    cleared = client.patch(f"/api/v2/tasks/{task['id']}", json={"assignee_emails": []})

    assert cleared.status_code == 200
    assert cleared.json()["assignees"] == []
    assert client.get("/api/v2/tasks").json()["items"] == []


def test_one_unknown_address_writes_nothing_at_all(client: TestClient) -> None:
    """The refusal is about the request rather than one field, so a list with a
    bad address in it does not half-apply -- the answer `assign_owner` gives."""
    signup(client, "owner@example.com", "Owner")
    login(client, "owner@example.com")
    opportunity = create_opportunity(client)
    task = create_task(client, opportunity["id"], assignee_emails=["owner@example.com"])

    refused = client.patch(
        f"/api/v2/tasks/{task['id']}",
        json={"assignee_emails": ["owner@example.com", "nobody@example.com"]},
    )

    assert refused.status_code == 422
    assert "nobody@example.com" in refused.json()["error"]["message"]
    assert len(task_by_id(client, opportunity["id"], task["id"])["assignees"]) == 1


def task_by_id(client: TestClient, opportunity_id: int, task_id: int) -> dict:
    items = client.get(f"/api/v2/opportunities/{opportunity_id}/tasks").json()["items"]
    return next(item for item in items if item["id"] == task_id)


def test_the_history_records_the_whole_set_and_can_put_it_back(client: TestClient) -> None:
    """Invariant 8 read against a set (milestone 4.6): the snapshot is the list,
    and a restore writes the list back -- which `apply_version` cannot do on its
    own, because a set is a table rather than a column."""
    signup(client, "owner@example.com", "Owner")
    signup(client, "gavin@example.com", "Gavin")
    signup(client, "max@example.com", "Maximilian")
    login(client, "owner@example.com")
    opportunity = create_opportunity(client)
    share(client, opportunity["id"], "gavin@example.com", "editor")
    share(client, opportunity["id"], "max@example.com", "editor")
    task = create_task(client, opportunity["id"], assignee_emails=["gavin@example.com"])

    assert (
        client.patch(
            f"/api/v2/tasks/{task['id']}",
            json={"assignee_emails": ["gavin@example.com", "max@example.com"]},
        ).status_code
        == 200
    )

    versions = client.get(f"/api/v2/tasks/{task['id']}/versions").json()["items"]
    assert [[item["name"] for item in version["assignees"]] for version in versions] == [
        ["Gavin"],
        ["Gavin", "Maximilian"],
    ]

    restored = client.post(f"/api/v2/tasks/{task['id']}/versions/1/restore")
    assert restored.status_code == 200
    assert [item["name"] for item in restored.json()["assignees"]] == ["Gavin"]
    # The restore is itself an edit, so the history grew rather than rewound.
    after = client.get(f"/api/v2/tasks/{task['id']}/versions").json()["items"]
    assert [[item["name"] for item in version["assignees"]] for version in after] == [
        ["Gavin"],
        ["Gavin", "Maximilian"],
        ["Gavin"],
    ]


def test_restoring_the_same_set_writes_nothing(client: TestClient) -> None:
    """D-120, which needed the canonical ordering to keep working: two
    snapshots of the same people have to compare equal as strings."""
    signup(client, "owner@example.com", "Owner")
    signup(client, "gavin@example.com", "Gavin")
    login(client, "owner@example.com")
    opportunity = create_opportunity(client)
    share(client, opportunity["id"], "gavin@example.com", "editor")
    task = create_task(client, opportunity["id"], assignee_emails=["gavin@example.com"])

    assert client.post(f"/api/v2/tasks/{task['id']}/versions/1/restore").status_code == 200

    versions = client.get(f"/api/v2/tasks/{task['id']}/versions").json()["items"]
    assert len(versions) == 1
