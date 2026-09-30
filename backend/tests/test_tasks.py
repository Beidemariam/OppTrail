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
    assert task["assignee_id"] is None
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

    task = create_task(client, opportunity["id"], assignee_email="GAVIN@example.com")

    assert task["assignee_id"] == colleague["id"]
    assert task["assignee_name"] == "Gavin"

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

    create_task(client, opportunity["id"], assignee_email="owner@example.com")

    assert client.get("/api/v2/notifications?type=task_assigned").json()["items"] == []


def test_an_unknown_assignee_is_refused_before_anything_is_written(
    client: TestClient,
) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)

    response = client.post(
        f"/api/v2/opportunities/{opportunity['id']}/tasks",
        json={"title": "Call back", "assignee_email": "nobody@example.com"},
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
    task = create_task(client, opportunity["id"], assignee_email="gavin@example.com")
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
    task = create_task(client, opportunity["id"], assignee_email="gavin@example.com")
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
        client, shared["id"], title="On the shared deal", assignee_email="gavin@example.com"
    )
    create_task(
        client, private["id"], title="On the private deal", assignee_email="gavin@example.com"
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
    done = create_task(client, opportunity["id"], title="Done", assignee_email="owner@example.com")
    create_task(client, opportunity["id"], title="Open", assignee_email="owner@example.com")
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
        assignee_email="owner@example.com",
        due_date=days_from_now(-2),
    )
    create_task(
        client,
        opportunity["id"],
        title="Later",
        assignee_email="owner@example.com",
        due_date=days_from_now(4),
    )
    create_task(client, opportunity["id"], title="No date", assignee_email="owner@example.com")

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
    task = create_task(client, opportunity["id"], assignee_email="owner@example.com")

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
        assignee_email="gavin@example.com",
        due_date=days_from_now(4),
    )
    create_task(
        client,
        opportunity["id"],
        title="Mine, this month",
        assignee_email="owner@example.com",
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
        assignee_email="owner@example.com",
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
