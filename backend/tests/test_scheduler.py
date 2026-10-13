"""The scheduler and its two jobs (milestone 6.5, ADR 0004).

Split the way ADR 0004 asks for — *"keep job functions free of framework
coupling so they stay directly testable"* — so almost everything here calls
`jobs.py` directly and only two tests involve APScheduler at all:

- **what a tick does** is `jobs.run_automations` and `jobs.run_backup`, called
  as functions,
- **that a tick is recorded** is `jobs.run_job`, including the failure path,
  because a silently dead scheduler is the production failure this table
  exists to make visible (`docs/ARCHITECTURE.md`, Observability),
- **that the scheduler is wired at all** is the two tests that start it.

The `client` fixture disables the scheduler (`conftest.py`), so a test that
wants one turns it back on deliberately.
"""

import asyncio
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_automations import closing_in, create_rule, runs_for, silence, timeline
from test_tasks import create_opportunity, signup

from app import jobs, scheduler
from app.database import db_connection
from app.settings import settings


def job_rows(job: str | None = None) -> list[sqlite3.Row]:
    with db_connection() as connection:
        if job is None:
            return list(connection.execute("SELECT * FROM job_runs ORDER BY id").fetchall())
        return list(
            connection.execute(
                "SELECT * FROM job_runs WHERE job = ? ORDER BY id",
                (job,),
            ).fetchall()
        )


# --- What a tick does -------------------------------------------------------


def test_the_acceptance_criterion_a_quiet_deal_gets_a_task_from_the_clock(
    client: TestClient,
) -> None:
    """Phase 6's acceptance criterion, now met by the clock rather than by a
    person pressing Run: *"a no-activity-for-14-days rule fires once, creates
    a task, and logs a system entry naming the rule."*

    `jobs.run_automations` is what the timer calls, so this is the real path
    with the timer taken out of it.
    """
    signup(client, "clockwork@example.com", "Clockwork")
    opportunity = create_opportunity(client, "Gone quiet")
    rule = create_rule(
        client,
        name="Chase the quiet ones",
        trigger_type="no_activity",
        trigger={"days": 14},
        action_type="create_task",
        action={"title": "Chase this deal", "due_in_days": 2},
    )
    silence(opportunity["id"])

    detail = jobs.run_automations()

    assert "1 rules" in detail
    tasks = client.get(f"/api/v2/opportunities/{opportunity['id']}/tasks").json()["items"]
    assert [task["title"] for task in tasks] == ["Chase this deal"]
    named = [
        entry
        for entry in timeline(client, opportunity["id"])
        if entry["system_generated"] and rule["name"] in entry["body"]
    ]
    assert len(named) == 1


def test_a_tick_does_not_nudge_the_same_quiet_deal_every_fifteen_minutes(
    client: TestClient,
) -> None:
    """The question a timer raises and a button never did: ninety-six ticks a
    day against a deal that is quiet *because* nobody is looking at it.

    The answer for `no_activity` is that the trigger rate limits itself, and
    the mechanism is §11's own traceability requirement: every action writes a
    system entry, and that entry **is** activity on the deal -- so a nudged
    deal stops being silent and cannot be a candidate again until another full
    window of silence has passed (**D-182**). One task, and the later ticks
    see no candidate at all rather than a suppressed one.
    """
    signup(client, "once@example.com", "Once")
    opportunity = create_opportunity(client, "Still quiet")
    rule = create_rule(
        client,
        trigger_type="no_activity",
        trigger={"days": 14},
        action_type="create_task",
        action={"title": "Chase it"},
    )
    silence(opportunity["id"])

    jobs.run_automations()
    jobs.run_automations()
    jobs.run_automations()

    tasks = client.get(f"/api/v2/opportunities/{opportunity['id']}/tasks").json()["items"]
    assert len(tasks) == 1, "a timer must not create a task per tick"
    assert [run["outcome"] for run in runs_for(client, rule["id"])] == ["applied"]


def test_a_quiet_spell_after_the_nudge_arms_the_rule_again(client: TestClient) -> None:
    """The other side of that: the rule is rate limited, not spent. A deal
    that is chased, stays quiet for another fortnight, and is still quiet is a
    deal worth chasing twice."""
    signup(client, "again@example.com", "Again")
    opportunity = create_opportunity(client, "Quiet twice")
    create_rule(
        client,
        trigger_type="no_activity",
        trigger={"days": 14},
        action_type="create_task",
        action={"title": "Chase it"},
    )
    silence(opportunity["id"])
    jobs.run_automations()

    # Another fortnight of silence, including over the nudge's own entry.
    silence(opportunity["id"])
    jobs.run_automations()

    tasks = client.get(f"/api/v2/opportunities/{opportunity['id']}/tasks").json()["items"]
    assert len(tasks) == 2


def test_a_close_date_rule_acts_once_per_window(client: TestClient) -> None:
    """`close_date_approaching` has no feedback loop -- the entry it writes
    does not move the close date -- so it is the trigger that needs the
    suppression D-182 adds, with its own `days` as the unit."""
    signup(client, "closing@example.com", "Closing")
    opportunity = create_opportunity(client, "Closing soon")
    client.patch(
        f"/api/v2/opportunities/{opportunity['id']}",
        json={"expected_close_date": closing_in(3)},
    )
    rule = create_rule(
        client,
        name="Closing this week",
        trigger_type="close_date_approaching",
        trigger={"days": 7},
        action_type="create_task",
        action={"title": "Prepare the paperwork"},
    )

    jobs.run_automations()
    jobs.run_automations()
    jobs.run_automations()

    tasks = client.get(f"/api/v2/opportunities/{opportunity['id']}/tasks").json()["items"]
    assert len(tasks) == 1, "a timer must not create a task per tick"
    outcomes = [(run["outcome"], run["reason"]) for run in runs_for(client, rule["id"])]
    assert outcomes[0][0] == "applied"
    assert [outcome for outcome, _ in outcomes[1:]] == ["skipped", "skipped"]
    assert "within this rule's 7-day window" in outcomes[1][1]


def test_a_preview_does_not_suppress_the_run_it_previews(client: TestClient) -> None:
    """The one way to get D-182 subtly wrong. A dry run records an `applied`
    row with `dry_run = 1`, so a suppression that counted those would mean
    pressing Preview disarmed the rule."""
    signup(client, "preview@example.com", "Preview")
    opportunity = create_opportunity(client, "Previewed first")
    client.patch(
        f"/api/v2/opportunities/{opportunity['id']}",
        json={"expected_close_date": closing_in(3)},
    )
    rule = create_rule(
        client,
        trigger_type="close_date_approaching",
        trigger={"days": 7},
        action_type="create_task",
        action={"title": "Prepare the paperwork"},
    )

    assert len(client.post(f"/api/v2/automation-rules/{rule['id']}/run").json()["runs"]) == 1
    jobs.run_automations()

    tasks = client.get(f"/api/v2/opportunities/{opportunity['id']}/tasks").json()["items"]
    assert len(tasks) == 1


def test_a_tick_walks_only_the_triggers_the_clock_owns(client: TestClient) -> None:
    """The three event-driven triggers are fired by the route that performed
    the write. A tick walking them too would act on every matching deal every
    fifteen minutes, which is the opposite of what "when a deal's stage
    changes" means."""
    signup(client, "scoped@example.com", "Scoped")
    opportunity = create_opportunity(client, "Not a tick's business")
    watcher = create_rule(
        client,
        name="On a stage change",
        trigger_type="stage_changed",
        trigger={},
        action_type="add_entry",
        action={"title": "Should not appear"},
    )
    silence(opportunity["id"])

    detail = jobs.run_automations()

    assert "0 rules" in detail
    assert runs_for(client, watcher["id"]) == []


def test_an_archived_or_disabled_rule_is_not_ticked(client: TestClient) -> None:
    signup(client, "parked@example.com", "Parked")
    create_opportunity(client, "Left alone")
    disabled = create_rule(client, name="Disabled", enabled=False)
    archived = create_rule(client, name="Archived")
    assert client.post(f"/api/v2/automation-rules/{archived['id']}/archive").status_code == 200
    silence(1)

    assert "0 rules" in jobs.run_automations()
    assert runs_for(client, disabled["id"]) == []


# --- The backup, unattended -------------------------------------------------


def test_the_scheduled_backup_writes_a_snapshot_that_restores(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase 6's other acceptance criterion: *"a scheduled backup runs
    unattended and its snapshot restores (ADR 0011) -- the first time backups
    are exercised by anything other than a person typing `make backup`."*

    The round trip itself is `tests/test_backup.py`'s; what this adds is that
    the job the scheduler calls produces a snapshot with the data in it.
    """
    monkeypatch.setattr(settings, "backup_dir", str(tmp_path / "snapshots"))
    signup(client, "snapshot@example.com", "Snapshot")
    create_opportunity(client, "Worth keeping")

    name = jobs.run_backup()

    snapshot = tmp_path / "snapshots" / name
    assert snapshot.exists()
    copy = sqlite3.connect(snapshot)
    try:
        names = [row[0] for row in copy.execute("SELECT name FROM opportunities")]
    finally:
        copy.close()
    assert names == ["Worth keeping"]


def test_the_retention_window_applies_to_a_scheduled_snapshot(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`backup_retention_count` already assumed a daily snapshot when it kept
    seven; until 6.5 nothing took one on a schedule, so nothing ever pruned
    unattended either."""
    monkeypatch.setattr(settings, "backup_dir", str(tmp_path / "snapshots"))
    monkeypatch.setattr(settings, "backup_retention_count", 2)
    signup(client, "pruned@example.com", "Pruned")

    for _ in range(4):
        jobs.run_backup()

    assert len(list((tmp_path / "snapshots").glob("app-*.db"))) == 2


# --- That a run is recorded -------------------------------------------------


def test_a_run_is_recorded_from_start_to_finish(client: TestClient) -> None:
    signup(client, "recorded@example.com", "Recorded")

    jobs.run_job("automations")

    rows = job_rows("automations")
    assert len(rows) == 1
    assert rows[0]["status"] == "succeeded"
    assert rows[0]["finished_at"] is not None
    assert "rules" in rows[0]["detail"]


def test_a_failing_job_is_recorded_rather_than_raised(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """There is nobody to answer a tick, so the row is the report. A job that
    raised would be swallowed by APScheduler's own logging and the failure
    would be invisible -- which is the exact failure mode this table exists
    for."""
    signup(client, "broken@example.com", "Broken")

    def explode() -> str:
        raise RuntimeError("the disk is full")

    monkeypatch.setitem(jobs.JOBS, "backup", explode)
    jobs.run_job("backup")

    rows = job_rows("backup")
    assert [row["status"] for row in rows] == ["failed"]
    assert rows[0]["detail"] == "RuntimeError: the disk is full"
    assert rows[0]["finished_at"] is not None


def test_a_row_left_at_started_is_what_an_interrupted_job_looks_like(
    client: TestClient,
) -> None:
    """Not an assertion about a crash, which a test cannot stage -- an
    assertion about the *shape* a crash leaves, which is why the row is
    written on start rather than on finish."""
    signup(client, "interrupted@example.com", "Interrupted")

    with db_connection() as connection:
        jobs.start_job(connection, "automations")

    rows = job_rows("automations")
    assert rows[0]["status"] == "started"
    assert rows[0]["finished_at"] is None


def test_the_health_probe_reports_the_latest_run_of_each_job(client: TestClient) -> None:
    """`docs/ARCHITECTURE.md`'s Observability requirement, from the endpoint
    whatever is watching this container already reads."""
    signup(client, "probe@example.com", "Probe")
    jobs.run_job("automations")
    jobs.run_job("automations")

    health = client.get("/api/health").json()

    assert [job["job"] for job in health["jobs"]] == ["automations"]
    assert health["jobs"][0]["status"] == "succeeded"
    # The *latest*, not every run: two runs, one row.
    assert health["jobs"][0]["id"] == job_rows("automations")[-1]["id"]


def test_the_log_is_read_newest_first_and_pages(client: TestClient) -> None:
    signup(client, "log@example.com", "Log")
    for _ in range(3):
        jobs.run_job("automations")

    first = client.get("/api/v2/job-runs?limit=2").json()
    assert len(first["items"]) == 2
    assert first["next_cursor"] is not None
    assert first["items"][0]["id"] > first["items"][1]["id"], "newest first"

    second = client.get(f"/api/v2/job-runs?limit=2&cursor={first['next_cursor']}").json()
    assert len(second["items"]) == 1
    assert second["next_cursor"] is None


# --- That the scheduler itself is wired -------------------------------------


def test_the_scheduler_schedules_both_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    """The only test that involves APScheduler. It asserts the wiring and not
    the timing: an interval trigger's first firing is one interval away, so a
    test that waited for a tick would wait fifteen minutes.

    Inside `asyncio.run` because `AsyncIOScheduler.start()` adopts the running
    loop -- which is exactly why it belongs in FastAPI's `lifespan` and
    nowhere else.
    """
    monkeypatch.setattr(settings, "scheduler_enabled", True)

    async def start_and_inspect() -> None:
        try:
            started = scheduler.start_scheduler()
            assert started is not None
            assert scheduler.scheduled_jobs() == ["automations", "backup"]
            # Idempotent: `lifespan` runs once, but a second call must not
            # stand up a second scheduler that would double every job.
            assert scheduler.start_scheduler() is started
        finally:
            scheduler.stop_scheduler()

    asyncio.run(start_and_inspect())
    assert scheduler.scheduled_jobs() == []


def test_the_scheduler_can_be_switched_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Which is what the test suite does, and what a deployment that runs the
    jobs some other way would do."""
    monkeypatch.setattr(settings, "scheduler_enabled", False)
    assert scheduler.start_scheduler() is None
    assert scheduler.scheduled_jobs() == []


def test_the_detail_line_counts_outcomes_rather_than_rows(client: TestClient) -> None:
    """Found by reading the live scheduler's own log rather than by a test:
    it reported *"2 deals considered, 2 acted on"* for a tick that wrote
    nothing, because a `skipped` run is a row too. A detail line nobody can
    trust is worse than no detail line."""
    signup(client, "counted@example.com", "Counted")
    acted_on = create_opportunity(client, "Will be acted on")
    client.patch(
        f"/api/v2/opportunities/{acted_on['id']}",
        json={"expected_close_date": closing_in(3)},
    )
    rule = create_rule(
        client,
        trigger_type="close_date_approaching",
        trigger={"days": 7},
        action_type="create_task",
        action={"title": "Prepare the paperwork"},
    )

    assert "1 acted on, 0 skipped" in jobs.run_automations()
    # The second tick is inside the rule's window, so it declines -- and says
    # so as a skip rather than as an action.
    assert "0 acted on, 1 skipped" in jobs.run_automations()
    assert [run["outcome"] for run in runs_for(client, rule["id"])] == [
        "applied",
        "skipped",
    ]
