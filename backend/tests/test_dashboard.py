"""The six dashboard aggregations (milestone 6.2, `docs/FEATURES.md` §10).

Two kinds of test here, and the second is the unusual one:

- **What each metric means.** Pipeline excludes closed deals, a win rate with
  nothing closed is `None` rather than 0%, time in stage says how far back it
  can be trusted, the stalled list is the board's own 14-day rule asked across
  every deal, and every number is filtered by what the caller may read.
- **What each metric costs.** §10's acceptance criterion is a 300 ms budget
  "at seeded scale, asserted in CI", and that assertion is
  `test_each_aggregate_answers_inside_the_budget` below. It is the only test
  in this project that builds a corpus the size the spec names, and it is the
  reason two of the six were rewritten: the obvious formulations measured
  1,533 ms and 408 ms (**D-172**).
"""

import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from test_tasks import create_opportunity, login, logout, share, signup
from test_timeline import create_entry

from app import dashboard
from app.database import db_connection
from app.settings import settings
from app.time_utils import utc_days_ago, utc_now


def dashboard_of(client: TestClient, **params: object) -> dict:
    query = "&".join(f"{key}={value}" for key, value in params.items())
    response = client.get(f"/api/v2/dashboard{'?' + query if query else ''}")
    assert response.status_code == 200, response.json()
    return response.json()


def opportunity_with_stage(client: TestClient, name: str, stage: str, value: str) -> dict:
    response = client.post(
        "/api/v2/opportunities",
        json={"name": name, "account_name": name, "stage": stage, "value": value},
    )
    assert response.status_code == 201, response.json()
    return response.json()


def test_pipeline_counts_open_stages_and_excludes_the_closed_ones(
    client: TestClient,
) -> None:
    signup(client, "owner@example.com", "Owner")
    opportunity_with_stage(client, "Acme", "Proposal", "50000")
    opportunity_with_stage(client, "Globex", "Proposal", "20000")
    opportunity_with_stage(client, "Won", "Closed Won", "80000")
    opportunity_with_stage(client, "Lost", "Closed Lost", "30000")

    pipeline = {row["stage"]: row for row in dashboard_of(client)["pipeline"]}

    assert pipeline["Proposal"]["deals"] == 2
    assert pipeline["Proposal"]["value"] == "70000"
    # Pipeline is what might still be won, so a closed deal is not in it --
    # §10's "non-deleted, non-closed".
    assert "Closed Won" not in pipeline
    assert "Closed Lost" not in pipeline
    # Every open stage appears, at zero: a stage missing from a chart reads as
    # a rendering fault rather than as an empty column.
    assert pipeline["Negotiation"] == {
        "stage": "Negotiation",
        "deals": 0,
        "value": "0",
    }


def test_a_win_rate_with_nothing_closed_is_not_zero(client: TestClient) -> None:
    """A team that has closed nothing has no win rate. 0% would read as having
    lost everything, which is a different claim."""
    signup(client, "owner@example.com", "Owner")
    opportunity_with_stage(client, "Acme", "Proposal", "50000")

    assert dashboard_of(client)["win_loss"] == {
        "won": 0,
        "lost": 0,
        "won_value": "0",
        "rate": None,
    }

    opportunity_with_stage(client, "Won", "Closed Won", "80000")
    opportunity_with_stage(client, "Lost", "Closed Lost", "30000")
    win_loss = dashboard_of(client)["win_loss"]
    assert (win_loss["won"], win_loss["lost"], win_loss["rate"]) == (1, 1, 0.5)
    assert win_loss["won_value"] == "80000"


def test_time_in_stage_says_how_far_back_it_can_be_trusted(
    client: TestClient,
) -> None:
    """§10's own caveat, and the reason this metric carries a second field:
    "only correct back to the point stage-change entries began being recorded;
    earlier history is absent and should be labelled as such rather than
    silently shown as zero"."""
    signup(client, "owner@example.com", "Owner")
    opportunity = create_opportunity(client)

    # Nothing has moved yet, so every stage is unmeasured -- `None`, not 0.
    empty = dashboard_of(client)["time_in_stage"]
    assert empty["earliest_change"] is None
    assert all(stage["average_days"] is None for stage in empty["stages"])
    assert all(stage["spans"] == 0 for stage in empty["stages"])

    for stage in ("Qualification", "Needs Analysis", "Proposal"):
        assert (
            client.patch(
                f"/api/v2/opportunities/{opportunity['id']}", json={"stage": stage}
            ).status_code
            == 200
        )
    # The stage changes land within one second of each other, so the spans are
    # real but zero-length; backdate the first two so the average is a number
    # somebody could read. Second-resolution timestamps are D-067.
    with db_connection() as connection:
        changes = connection.execute(
            """
            SELECT id FROM timeline_entries
            WHERE type = 'stage_change' ORDER BY id
            """
        ).fetchall()
        for offset, row in enumerate(changes):
            connection.execute(
                "UPDATE timeline_entries SET event_timestamp = ? WHERE id = ?",
                (utc_days_ago(30 - offset * 10), row["id"]),
            )
        connection.commit()

    measured = dashboard_of(client)["time_in_stage"]
    by_stage = {stage["stage"]: stage for stage in measured["stages"]}
    # Ten days from the move into Qualification to the move into Needs
    # Analysis, which is time spent in Qualification.
    assert by_stage["Qualification"]["average_days"] == pytest.approx(10, abs=0.01)
    assert by_stage["Qualification"]["spans"] == 1
    # The last change has nothing after it, so Proposal is still unmeasured.
    assert by_stage["Proposal"]["average_days"] is None
    assert measured["earliest_change"] is not None


def test_the_stalled_list_is_the_boards_rule_across_every_deal(
    client: TestClient,
) -> None:
    signup(client, "owner@example.com", "Owner")
    quiet = create_opportunity(client, "Gone quiet")
    busy = create_opportunity(client, "Still moving")
    closed = opportunity_with_stage(client, "Finished", "Closed Won", "10000")
    create_entry(client, closed["id"], title="Signed")

    # Everything on the quiet deal, and on the closed one, happened a month
    # ago; the busy one has something from today.
    with db_connection() as connection:
        connection.execute(
            """
            UPDATE timeline_entries
            SET event_timestamp = ?, created_at = ?
            WHERE opportunity_id IN (?, ?)
            """,
            (utc_days_ago(30), utc_days_ago(30), quiet["id"], closed["id"]),
        )
        connection.commit()
    create_entry(client, busy["id"], title="Call today", event_timestamp=utc_now())

    stalled = dashboard_of(client)["stalled"]

    assert [row["name"] for row in stalled] == ["Gone quiet"]
    # A closed deal is not stalled, it is finished.
    assert all(row["stage"] not in ("Closed Won", "Closed Lost") for row in stalled)
    assert stalled[0]["last_activity_at"] < utc_days_ago(dashboard.STALLED_AFTER_DAYS)


def test_activity_is_grouped_by_author_and_week(client: TestClient) -> None:
    owner = signup(client, "owner@example.com", "Owner")
    assert owner
    opportunity = create_opportunity(client)
    create_entry(client, opportunity["id"], title="One")
    create_entry(client, opportunity["id"], title="Two")

    signup(client, "editor@example.com", "Editor")
    logout(client)
    login(client, "owner@example.com")
    share(client, opportunity["id"], "editor@example.com", "editor")
    logout(client)
    login(client, "editor@example.com")
    create_entry(client, opportunity["id"], title="Theirs")
    logout(client)
    login(client, "owner@example.com")

    activity = dashboard_of(client)["activity"]
    by_author = {row["author_name"]: row["items"] for row in activity}

    # The owner's two entries, the "Opportunity created" system entry, and
    # the one sharing wrote -- a system entry has an author and this metric
    # counts what a person caused, including by granting access.
    assert by_author["Owner"] == 4
    assert by_author["Editor"] == 1
    assert all(len(row["week"]) == 7 for row in activity)


def test_the_forecast_shows_the_ramp_it_used(client: TestClient, monkeypatch) -> None:
    """A forecast whose assumptions nobody can see is a number nobody should
    act on, so the probabilities come back beside the total."""
    signup(client, "owner@example.com", "Owner")
    opportunity_with_stage(client, "Acme", "Proposal", "100000")
    opportunity_with_stage(client, "Globex", "Negotiation", "50000")

    forecast = dashboard_of(client)["forecast"]
    # 100000 * 0.6 + 50000 * 0.8
    assert forecast["weighted_value"] == "100000.00"
    assert {row["stage"]: row["probability"] for row in forecast["stages"]} == {
        "Proposal": 0.6,
        "Negotiation": 0.8,
    }

    # Configurable, and a partial configuration keeps the defaults for every
    # stage it leaves out (§10's "configurable probabilities").
    monkeypatch.setattr(settings, "forecast_probabilities", {"Proposal": 0.5})
    tuned = dashboard_of(client)["forecast"]
    assert tuned["weighted_value"] == "90000.00"
    assert {row["stage"]: row["probability"] for row in tuned["stages"]} == {
        "Proposal": 0.5,
        "Negotiation": 0.8,
    }


def test_every_number_is_filtered_by_what_the_caller_may_read(
    client: TestClient,
) -> None:
    """The dashboard is the second read in the app that spans opportunities,
    so permissions are inside each query rather than a filter over its results
    (the first was search). Two managers asking the same question get
    different answers, which is correct."""
    signup(client, "owner@example.com", "Owner")
    shared = create_opportunity(client, "Shared deal")
    opportunity_with_stage(client, "Private deal", "Negotiation", "999999")
    signup(client, "viewer@example.com", "Viewer")
    signup(client, "outsider@example.com", "Outsider")
    logout(client)
    login(client, "owner@example.com")
    share(client, shared["id"], "viewer@example.com", "viewer")
    logout(client)

    login(client, "viewer@example.com")
    seen = dashboard_of(client)
    pipeline = {row["stage"]: row["deals"] for row in seen["pipeline"]}
    assert pipeline["Prospecting"] == 1
    # The private deal's 999,999 is in neither the pipeline nor the forecast.
    assert pipeline["Negotiation"] == 0
    # The forecast counts the shared deal and not the private one: its own
    # Prospecting value at 0.1, and nothing from the 999,999 in Negotiation
    # that would have weighted to 799,999.20.
    expected = Decimal(shared["value"]) * Decimal("0.1")
    assert Decimal(seen["forecast"]["weighted_value"]) == expected
    logout(client)

    login(client, "outsider@example.com")
    nothing = dashboard_of(client)
    assert all(row["deals"] == 0 for row in nothing["pipeline"])
    assert nothing["win_loss"]["rate"] is None
    assert nothing["stalled"] == []
    assert nothing["activity"] == []
    assert nothing["forecast"]["weighted_value"] == "0.00"


def test_the_reading_windows_are_bounded(client: TestClient) -> None:
    """Not paginated, unlike every other collection read: these are six fixed
    summaries rather than a list somebody walks, so the two that could grow
    take caps instead. A cursor over an aggregate is a cursor over something
    that changes under it."""
    signup(client, "owner@example.com", "Owner")
    assert client.get("/api/v2/dashboard?weeks=0").status_code == 422
    assert client.get("/api/v2/dashboard?weeks=53").status_code == 422
    assert client.get("/api/v2/dashboard?stalled_limit=0").status_code == 422
    assert client.get("/api/v2/dashboard?stalled_limit=201").status_code == 422
    assert client.get("/api/v2/dashboard?weeks=52&stalled_limit=200").status_code == 200


def build_seeded_scale(connection, opportunities: int, entries: int) -> None:
    """§10's corpus: 400 opportunities and ~800,000 activity rows.

    Spread across two years rather than all stamped now, because that is what
    a database holding this many rows looks like and because one of the six
    metrics reads a *window* of it -- a fixture with every row inside that
    window measures something no deployment will ever ask.
    """
    stamp = "%Y-%m-%dT%H:%M:%SZ"
    base = datetime.now(UTC) - timedelta(days=730)

    def spread(index: int, total: int) -> str:
        return (base + timedelta(seconds=int(730 * 86400 * index / total))).strftime(stamp)

    now = utc_now()
    connection.executemany(
        "INSERT INTO users (email, password_hash, name, created_at) VALUES (?, ?, ?, ?)",
        [(f"rep{rep}@example.com", "x", f"Rep {rep}", now) for rep in range(6)],
    )
    stages = ["Prospecting", "Qualification", "Proposal", "Negotiation", "Closed Won"]
    connection.executemany(
        """
        INSERT INTO opportunities
            (name, account_name, value, currency, stage, owner_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 1, ?, ?)
        """,
        [
            (f"Deal {i}", f"Account {i}", 1000 + i, "USD", stages[i % 5], now, now)
            for i in range(opportunities)
        ],
    )
    note_rows = entries // 4
    comment_rows = entries // 12
    connection.executemany(
        """
        INSERT INTO timeline_entries
            (opportunity_id, type, title, body, event_timestamp, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                (i % opportunities) + 1,
                "stage_change" if i % 500 == 0 else "call",
                "Stage changed to Proposal" if i % 500 == 0 else f"Entry {i}",
                "body",
                spread(i, entries),
                (i % 6) + 1,
                spread(i, entries),
            )
            for i in range(entries)
        ],
    )
    connection.executemany(
        """
        INSERT INTO notes (entry_id, body, created_by, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            ((i % entries) + 1, "note", (i % 6) + 1, spread(i, note_rows), now)
            for i in range(note_rows)
        ],
    )
    connection.executemany(
        "INSERT INTO comments (note_id, body, created_by, created_at) VALUES (?, ?, ?, ?)",
        [
            ((i % note_rows) + 1, "comment", (i % 6) + 1, spread(i, comment_rows))
            for i in range(comment_rows)
        ],
    )
    connection.commit()


def test_each_aggregate_answers_inside_the_budget(client: TestClient) -> None:
    """§10's acceptance criterion: "each dashboard aggregate returns inside
    300 ms at seeded scale, asserted in CI".

    This is the only test here that builds the corpus §10 names, and it is
    what the two rewrites in **D-172** came from -- measured against this
    fixture, the obvious formulation of activity-per-rep took 1,533 ms and the
    obvious one of the stalled list took 408 ms. The budget is asserted per
    metric rather than on the whole response, because that is what the
    criterion says and because one slow metric is a fixable thing while a slow
    total is not.

    The margin is reported in the failure message rather than asserted
    tightly: this runs on a developer's laptop and in a container, and a test
    that fails at 280 ms on a loaded machine teaches nobody anything. What it
    catches is a formulation that regresses by an order of magnitude, which is
    exactly what happened twice while this was being written.
    """
    signup(client, "manager@example.com", "Manager")
    with db_connection() as connection:
        build_seeded_scale(connection, opportunities=400, entries=600_000)
        activity_rows = sum(
            connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("timeline_entries", "notes", "comments")
        )
        assert activity_rows >= 800_000, activity_rows

        metrics = {
            "pipeline": lambda: dashboard.pipeline_by_stage(connection, 1),
            "win_loss": lambda: dashboard.win_loss(connection, 1, None),
            "time_in_stage": lambda: dashboard.average_time_in_stage(connection, 1),
            "stalled": lambda: dashboard.stalled_opportunities(connection, 1),
            "activity": lambda: dashboard.activity_per_rep(connection, 1),
            "forecast": lambda: dashboard.forecast(connection, 1),
        }
        measured = {}
        for name, metric in metrics.items():
            started = time.perf_counter()
            metric()
            measured[name] = (time.perf_counter() - started) * 1000

    over = {name: ms for name, ms in measured.items() if ms >= 300}
    assert not over, (
        f"over §10's 300 ms budget at {activity_rows:,} activity rows: {over}; "
        f"all six: { {name: round(ms, 1) for name, ms in measured.items()} }"
    )


def test_the_sums_say_which_currency_they_are_in(client: TestClient) -> None:
    """Four of the six add `value` across deals, and a deal carries its own
    currency -- so a mixed-currency deployment would get a total that is a
    number and not an amount. The answer says which currency, or says nothing,
    which is what lets the screen label it honestly."""
    signup(client, "owner@example.com", "Owner")
    opportunity_with_stage(client, "Acme", "Proposal", "100")
    assert dashboard_of(client)["currency"] == "USD"

    response = client.post(
        "/api/v2/opportunities",
        json={
            "name": "Globex",
            "account_name": "Globex",
            "stage": "Proposal",
            "value": "200",
            "currency": "EUR",
        },
    )
    assert response.status_code == 201
    assert dashboard_of(client)["currency"] is None
