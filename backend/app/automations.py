"""Automations: one trigger, ANDed conditions, one action (milestone 6.3).

`docs/FEATURES.md` §11 asks for *"a constrained, legible rule builder --
explicitly not a workflow engine"*, and five of its constraints are
implemented here rather than described anywhere:

- **One hop, structurally** (**D-174**). Nothing in this module calls
  `fire_event` or `run_rule`, so an automated write cannot trigger a rule and
  there is no loop to detect. `fire_event` is called from the route handlers
  that perform *human* writes, below the commit, where `publish_*` sits -- and
  the entries this module writes are `system_generated`, which no trigger
  looks at. `tests/test_automations.py::test_invariant_a_rule_cannot_trigger_a_rule`
  scans this file for the call, the way `test_soft_delete.py` scans for a hard
  delete: the guarantee is a thing the code must not *contain*.

- **A rule acts with its creator's authority** (**D-173**). It is evaluated
  only over opportunities its creator can read, every write is attributed to
  the creator, and the role required by the action is re-checked per deal at
  run time -- so a rule that changes a stage on a deal its creator does not
  own records `skipped` with the reason rather than performing a write nobody
  could have performed by hand. That is what makes creating a rule safe to
  leave open to any authenticated caller: a rule grants its author nothing
  they did not already have.

- **Dry run is the same code path**, with `apply` off: one function decides
  what would happen, and the mode decides whether it is written. A preview
  produced by separate code is a preview of something else.

- **Every applied action leaves a system entry naming the rule** -- §11's own
  requirement, and `AGENTS.md` standard 5's ("any non-user-initiated write
  must be traceable to the action that caused it"). `change_stage` and
  `add_entry` *are* that entry; `create_task` and `notify_user` get one
  beside what they wrote. The entry is `system_generated`, so it cannot be
  edited or deleted through the API, like every other system entry.

- **The clock is somebody else's job.** `no_activity` and
  `close_date_approaching` are evaluated by `run_rule`, which the manual
  run/preview route calls today and milestone 6.5's scheduler will call on a
  timer. There is no second evaluator to keep in agreement.
"""

import json
import sqlite3
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from .custom_fields import live_definitions, visible_values
from .dashboard import CLOSED_STAGES
from .database import db_connection
from .events import publish_opportunity_changed
from .logging_utils import logger
from .notification_service import create_notification
from .permissions import Role, get_opportunity_role
from .routes_tasks import TASK_ROWS_SQL
from .schemas import (
    CUSTOM_CONDITION_PREFIX,
    NUMERIC_CONDITION_FIELDS,
    AutomationCondition,
    AutomationOutcome,
    AutomationRunPublic,
)
from .time_utils import utc_days_ago, utc_now
from .timeline_utils import create_system_timeline_entry
from .versioning import OPPORTUNITY_VERSIONS, TASK_VERSIONS, record_version

# How many deals one manual or scheduled run will consider. §11 caps rules in
# number; this caps the work one firing can do, which is the other half of
# "legible" -- a rule that silently touches four hundred deals is not a rule
# anybody can dry-run and understand.
AUTOMATION_RUN_LIMIT = 200

RULE_ROWS_SQL = """
    SELECT automation_rules.id,
           automation_rules.name,
           automation_rules.trigger_type,
           automation_rules.trigger_config,
           automation_rules.conditions,
           automation_rules.action_type,
           automation_rules.action_config,
           automation_rules.enabled,
           automation_rules.created_by,
           users.name AS creator_name,
           automation_rules.created_at,
           automation_rules.updated_at,
           automation_rules.archived_at
    FROM automation_rules
    JOIN users ON users.id = automation_rules.created_by
"""

RUN_ROWS_SQL = """
    SELECT automation_runs.id,
           automation_runs.rule_id,
           automation_rules.name AS rule_name,
           automation_runs.opportunity_id,
           opportunities.name AS opportunity_name,
           automation_runs.outcome,
           automation_runs.reason,
           automation_runs.entry_id,
           automation_runs.dry_run,
           automation_runs.created_at
    FROM automation_runs
    JOIN automation_rules ON automation_rules.id = automation_runs.rule_id
    JOIN opportunities ON opportunities.id = automation_runs.opportunity_id
"""

# What role the rule's creator needs on a deal for each action, resolved
# against the same three roles every route resolves. `notify_user` needs only
# read access because telling somebody something changes nothing about the
# record; the other three write to it, so they are the timeline-write rule --
# except `change_stage`, which is a field on the opportunity and therefore
# owner-only, exactly as `PATCH /opportunities/{id}` is.
ACTION_REQUIRES: dict[str, tuple[Role, ...]] = {
    "notify_user": ("owner", "editor", "viewer"),
    "create_task": ("owner", "editor"),
    "add_entry": ("owner", "editor"),
    "change_stage": ("owner",),
}


def rule_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "trigger_type": row["trigger_type"],
        "trigger": json.loads(row["trigger_config"]),
        "conditions": json.loads(row["conditions"]),
        "action_type": row["action_type"],
        "action": json.loads(row["action_config"]),
        "enabled": bool(row["enabled"]),
        "created_by": row["created_by"],
        "creator_name": row["creator_name"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "archived_at": row["archived_at"],
    }


def run_from_row(row: sqlite3.Row) -> AutomationRunPublic:
    return AutomationRunPublic(
        id=row["id"],
        rule_id=row["rule_id"],
        rule_name=row["rule_name"],
        opportunity_id=row["opportunity_id"],
        opportunity_name=row["opportunity_name"],
        outcome=row["outcome"],
        reason=row["reason"],
        entry_id=row["entry_id"],
        dry_run=bool(row["dry_run"]),
        created_at=row["created_at"],
    )


# --- Conditions -------------------------------------------------------------


def _field_value(
    opportunity: sqlite3.Row,
    field: str,
    definitions: list[dict[str, Any]],
) -> str | None:
    """One comparable value off a deal, column or custom field alike.

    Custom values come through `visible_values`, so a condition naming an
    **archived** field finds nothing and the rule stops matching -- the same
    answer archiving already gives a saved view and a bookmarked URL
    (milestone 6.1). Reading the raw JSON instead would leave a rule acting on
    a field nobody can see on screen any more, which is the one outcome
    ADR 0006's never-trust-the-column-on-read rule exists to prevent.
    `None` is therefore both "not set" and "no longer defined", and `_matches`
    treats it as a failed comparison either way.
    """
    if field.startswith(CUSTOM_CONDITION_PREFIX):
        key = field[len(CUSTOM_CONDITION_PREFIX) :]
        values = visible_values(opportunity["custom_values"], definitions)
        if key not in values:
            return None
        value = values[key]
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, list):
            return ", ".join(str(item) for item in value)
        return str(value)
    raw = opportunity[field]
    return None if raw is None else str(raw)


def _ordered[T: (Decimal, str)](first: T, second: T, op: str) -> bool:
    """The five ordering operators over two values of one type.

    Generic so the numeric and the textual comparison are the same code read
    twice rather than two ladders that could disagree -- and so mypy sees one
    type on both sides, which a `Decimal | str` pair does not give it.
    """
    if op == "eq":
        return first == second
    if op == "ne":
        return first != second
    if op == "gt":
        return first > second
    if op == "gte":
        return first >= second
    if op == "lt":
        return first < second
    return first <= second


def _compare(left: str, op: str, right: str, numeric: bool) -> bool:
    if op == "contains":
        return right.casefold() in left.casefold()
    if numeric:
        try:
            return _ordered(Decimal(left), Decimal(right), op)
        except InvalidOperation:
            # `value` is a NUMERIC column, and SQLite will store text in one.
            # Nothing the API accepts can put it there (`OpportunityUpdate`
            # parses a Decimal), but a hand-edited or imported database can --
            # so fall through to the string comparison rather than raising. A
            # rule firing is not where a bad stored value should be
            # discovered, and the alternative is a 500 on somebody else's
            # write.
            pass
    return _ordered(left, right, op)


def _matches(
    opportunity: sqlite3.Row,
    conditions: list[dict[str, Any]],
    definitions: list[dict[str, Any]],
) -> str | None:
    """`None` if every condition holds, else the first one that did not.

    The reason is returned rather than a bare `False` because it is what the
    run log shows: "did not match: stage ne Closed Won" is the difference
    between a rule somebody can debug and a rule that silently does nothing.
    """
    for raw in conditions:
        condition = AutomationCondition.model_validate(raw)
        actual = _field_value(opportunity, condition.field, definitions)
        numeric = condition.field in NUMERIC_CONDITION_FIELDS
        if actual is None:
            return f"{condition.field} is not set"
        if not _compare(actual, condition.op, condition.value, numeric):
            return f"{condition.field} {condition.op} {condition.value} does not hold"
    return None


# --- Candidate selection ----------------------------------------------------


def _accessible_clause(creator_id: int) -> tuple[str, list[object]]:
    """The deals a rule may consider: exactly what its creator can read.

    The same correlated shape `dashboard._accessible` uses, because this is
    the third read in the app that spans opportunities and cannot resolve one
    role first.
    """
    return (
        """
        opportunities.deleted_at IS NULL
        AND (
            opportunities.owner_id = ?
            OR EXISTS (
                SELECT 1 FROM opportunity_shares
                WHERE opportunity_shares.opportunity_id = opportunities.id
                    AND opportunity_shares.user_id = ?
                    AND opportunity_shares.deleted_at IS NULL
            )
        )
        """,
        [creator_id, creator_id],
    )


OPPORTUNITY_COLUMNS = (
    "opportunities.id, opportunities.name, opportunities.account_name, "
    "opportunities.value, opportunities.currency, opportunities.stage, "
    "opportunities.owner_id, opportunities.expected_close_date, "
    "opportunities.custom_values"
)


def _no_activity_candidates(
    connection: sqlite3.Connection,
    creator_id: int,
    days: int,
) -> list[sqlite3.Row]:
    """Deals silent for N days, longest-silence-first.

    The grouped-union pass `dashboard.stalled_opportunities` arrived at under
    the 300 ms budget (**D-172**), asked with the rule's own window instead of
    the fixed fourteen days. Closed deals are excluded for the same reason
    they are there: a won deal is not stalled, it is finished -- and a rule
    nudging somebody about a closed deal is the rule nobody keeps enabled.
    """
    clause, params = _accessible_clause(creator_id)
    cutoff = utc_days_ago(days)
    return list(
        connection.execute(
            f"""
            WITH activity AS (
                SELECT opportunity_id, MAX(activity_at) AS last_activity_at
                FROM (
                    SELECT opportunity_id, event_timestamp AS activity_at
                    FROM timeline_entries
                    WHERE deleted_at IS NULL
                    UNION ALL
                    SELECT timeline_entries.opportunity_id, notes.created_at
                    FROM notes
                    JOIN timeline_entries ON timeline_entries.id = notes.entry_id
                    WHERE notes.deleted_at IS NULL
                        AND timeline_entries.deleted_at IS NULL
                    UNION ALL
                    SELECT timeline_entries.opportunity_id, comments.created_at
                    FROM comments
                    JOIN notes ON notes.id = comments.note_id
                    JOIN timeline_entries ON timeline_entries.id = notes.entry_id
                    WHERE comments.deleted_at IS NULL
                        AND notes.deleted_at IS NULL
                        AND timeline_entries.deleted_at IS NULL
                )
                GROUP BY opportunity_id
            )
            SELECT {OPPORTUNITY_COLUMNS}
            FROM opportunities
            JOIN activity ON activity.opportunity_id = opportunities.id
            WHERE {clause}
                AND opportunities.stage NOT IN ({", ".join("?" for _ in CLOSED_STAGES)})
                AND activity.last_activity_at < ?
            ORDER BY activity.last_activity_at, opportunities.id
            LIMIT ?
            """,
            (*params, *CLOSED_STAGES, cutoff, AUTOMATION_RUN_LIMIT),
        ).fetchall()
    )


def _close_date_candidates(
    connection: sqlite3.Connection,
    creator_id: int,
    days: int,
) -> list[sqlite3.Row]:
    """Open deals closing within N days, soonest first.

    The window opens at today rather than at the past: a close date that has
    already gone by is an overdue deal, which is a different question from an
    approaching one and would make this rule fire forever on every deal whose
    date slipped.
    """
    clause, params = _accessible_clause(creator_id)
    today = utc_now()[:10]
    horizon = (
        connection.execute("SELECT date(?, ?)", (today, f"+{days} days")).fetchone()[0] or today
    )
    return list(
        connection.execute(
            f"""
            SELECT {OPPORTUNITY_COLUMNS}
            FROM opportunities
            WHERE {clause}
                AND opportunities.stage NOT IN ({", ".join("?" for _ in CLOSED_STAGES)})
                AND opportunities.expected_close_date IS NOT NULL
                AND opportunities.expected_close_date >= ?
                AND opportunities.expected_close_date <= ?
            ORDER BY opportunities.expected_close_date, opportunities.id
            LIMIT ?
            """,
            (*params, *CLOSED_STAGES, today, horizon, AUTOMATION_RUN_LIMIT),
        ).fetchall()
    )


def _event_candidates(
    connection: sqlite3.Connection,
    creator_id: int,
    opportunity_id: int,
) -> list[sqlite3.Row]:
    """The one deal a human write happened on, if the rule's creator may read it."""
    clause, params = _accessible_clause(creator_id)
    row = connection.execute(
        f"""
        SELECT {OPPORTUNITY_COLUMNS}
        FROM opportunities
        WHERE opportunities.id = ? AND {clause}
        """,
        (opportunity_id, *params),
    ).fetchone()
    return [row] if row is not None else []


def _trigger_wants(rule: dict[str, Any], event: dict[str, Any]) -> str | None:
    """Whether the event that just happened is the one this rule watches.

    `None` to proceed, else why not. Event triggers only: a time trigger's
    selection is its query above.
    """
    config = rule["trigger"]
    if rule["trigger_type"] == "stage_changed":
        if config.get("to_stage") and event.get("to_stage") != config["to_stage"]:
            return f"stage did not change to {config['to_stage']}"
        if config.get("from_stage") and event.get("from_stage") != config["from_stage"]:
            return f"stage did not change from {config['from_stage']}"
        return None
    if rule["trigger_type"] == "entry_created":
        if config.get("entry_type") and event.get("entry_type") != config["entry_type"]:
            return f"entry was not of type {config['entry_type']}"
        return None
    # field_changed -- the route reports which fields its PATCH actually
    # moved, so a rule watching `value` is not woken by a rename.
    watched = config.get("field")
    if watched not in event.get("fields", []):
        return f"{watched} did not change"
    return None


# --- Actions ----------------------------------------------------------------


def _rule_note(rule: dict[str, Any]) -> str:
    """The sentence that makes an automated write traceable (§11).

    Named rather than id'd, because the person reading the timeline is being
    told why something appeared and a rule id means nothing to them. The id is
    in `automation_runs` for the person asking a forensic question.
    """
    return f'Automation rule "{rule["name"]}" did this.'


def _apply_create_task(
    connection: sqlite3.Connection,
    rule: dict[str, Any],
    opportunity: sqlite3.Row,
    actor_id: int,
) -> tuple[str, int]:
    action = rule["action"]
    now = utc_now()
    due_date = None
    if action.get("due_in_days") is not None:
        due_date = connection.execute(
            "SELECT date(?, ?)",
            (now[:10], f"+{action['due_in_days']} days"),
        ).fetchone()[0]
    assignee_id = (
        opportunity["owner_id"] if action.get("recipient", "owner") == "owner" else actor_id
    )
    cursor = connection.execute(
        """
        INSERT INTO tasks (
            opportunity_id, entry_id, title, description,
            due_date, created_by, created_at, updated_at
        )
        VALUES (?, NULL, ?, ?, ?, ?, ?, ?)
        """,
        (
            opportunity["id"],
            action["title"],
            action.get("body") or "",
            due_date,
            actor_id,
            now,
            now,
        ),
    )
    task_id = int(cursor.lastrowid or 0)
    # `set_assignees` is `routes_tasks`' own helper and importing a route
    # module here would be a cycle, so the one INSERT is written out. The join
    # table is still the only place an assignee is recorded (milestone 4.6).
    connection.execute(
        "INSERT INTO task_assignees (task_id, user_id, created_at) VALUES (?, ?, ?)",
        (task_id, assignee_id, now),
    )
    # Version 1 at creation, exactly as `routes_tasks.create_task` writes one
    # (milestone 4.2a). Not optional: a version is the state *after* a write,
    # so a task with no version 1 would lose its original wording to its own
    # first edit -- `AGENTS.md` invariant 8 ("edits are recoverable") broken by
    # the one writer nobody is watching.
    record_version(
        connection,
        TASK_VERSIONS,
        task_id,
        _task_row(connection, task_id, actor_id),
        actor_id,
        now,
    )
    entry_id = _write_system_entry(
        connection,
        rule,
        opportunity,
        actor_id,
        title=f"Task created: {action['title']}",
    )
    return f"created task {task_id}", entry_id


def _task_row(connection: sqlite3.Connection, task_id: int, creator_id: int) -> sqlite3.Row:
    """The task as `TASK_VERSIONS` needs to see it.

    `routes_tasks.TASK_ROWS_SQL` rather than a query written here, because
    `assignee_ids` has to be the *canonical* string -- ids ascending, comma
    separated -- that `versioning.version_is_current` compares as text
    (milestone 4.6). Two spellings of the same people would stop a restore
    being a no-op, so there is one expression and this reads it.
    """
    row: sqlite3.Row = connection.execute(
        # The rule's creator is the reader here, as everywhere else a rule
        # reads (D-173): a rule sees what its author would see by hand.
        f"{TASK_ROWS_SQL} WHERE tasks.id = ?",
        (creator_id, task_id),
    ).fetchone()
    return row


def _apply_notify_user(
    connection: sqlite3.Connection,
    rule: dict[str, Any],
    opportunity: sqlite3.Row,
    actor_id: int,
) -> tuple[str, int]:
    action = rule["action"]
    recipient_id = (
        opportunity["owner_id"] if action.get("recipient", "owner") == "owner" else actor_id
    )
    create_notification(
        connection,
        user_id=recipient_id,
        notification_type="automation",
        payload={
            "opportunity_id": opportunity["id"],
            "rule_id": rule["id"],
            "rule_name": rule["name"],
            "title": action["title"],
            "body": action.get("body"),
        },
    )
    entry_id = _write_system_entry(
        connection,
        rule,
        opportunity,
        actor_id,
        title=f"Notified: {action['title']}",
    )
    return f"notified user {recipient_id}", entry_id


def _apply_add_entry(
    connection: sqlite3.Connection,
    rule: dict[str, Any],
    opportunity: sqlite3.Row,
    actor_id: int,
) -> tuple[str, int]:
    """The action whose write *is* the traceable entry.

    It takes the rule's chosen entry type rather than forcing one, because
    "log a call-back reminder" and "log an objection follow-up" are different
    things to a reader filtering the timeline -- and it is `system_generated`
    like every other entry this module writes, so nobody can edit a record of
    what an automation did.
    """
    action = rule["action"]
    entry_id = _write_system_entry(
        connection,
        rule,
        opportunity,
        actor_id,
        title=action["title"],
        body=action.get("body") or "",
        entry_type=action.get("entry_type") or "other",
    )
    return "added a timeline entry", entry_id


def _apply_change_stage(
    connection: sqlite3.Connection,
    rule: dict[str, Any],
    opportunity: sqlite3.Row,
    actor_id: int,
) -> tuple[str, int]:
    """A stage change, recorded the way every stage change is.

    The `stage_change` system entry is this action's traceable entry rather
    than a second one beside it: the dashboard's time-in-stage reads that type
    (milestone 6.2) and writing an `other` entry here as well would put two
    records of one change on the timeline.

    It **does** record a version, like every other write to an opportunity
    (milestone 2.10). `AGENTS.md` invariant 8 says every user-editable field
    keeps its previous value attributed to who changed it, and that "quietly
    rewriting one must be [traceable] too" -- which is precisely what an
    unattended writer does. So the owner reads this in the history and can
    restore the stage it replaced. It does not double up in the activity feed:
    `activity.py` already drops an opportunity version whose only changed
    field is the stage, because the system entry below is that event's one
    appearance.
    """
    target = rule["action"]["stage"]
    now = utc_now()
    connection.execute(
        "UPDATE opportunities SET stage = ?, updated_at = ? WHERE id = ?",
        (target, now, opportunity["id"]),
    )
    moved = connection.execute(
        "SELECT * FROM opportunities WHERE id = ?",
        (opportunity["id"],),
    ).fetchone()
    record_version(
        connection,
        OPPORTUNITY_VERSIONS,
        int(opportunity["id"]),
        moved,
        actor_id,
        now,
    )
    entry_id = _write_system_entry(
        connection,
        rule,
        opportunity,
        actor_id,
        title=f"Stage changed to {target}",
        body=f"Stage changed from {opportunity['stage']} to {target}.",
        entry_type="stage_change",
    )
    return f"changed stage to {target}", entry_id


def _write_system_entry(
    connection: sqlite3.Connection,
    rule: dict[str, Any],
    opportunity: sqlite3.Row,
    actor_id: int,
    title: str,
    body: str = "",
    entry_type: str = "other",
) -> int:
    """§11's traceable entry, and the only way this module writes to a timeline.

    The rule's sentence is appended to the body rather than replacing it, so
    an `add_entry` action's own text is what the reader sees first and the
    attribution follows it. There is no `automation` entry type: `type`
    carries a CHECK constraint, so a new value is a full table rebuild
    (revision 0005 is the precedent), and §11 asks for an entry that names the
    rule rather than for a type that does. `system_generated = 1` is what
    marks it as not a person's writing, which is the distinction the API
    already enforces everywhere.
    """
    note = _rule_note(rule)
    create_system_timeline_entry(
        connection=connection,
        opportunity_id=opportunity["id"],
        created_by=actor_id,
        entry_type=entry_type,
        title=title,
        body=f"{body}\n\n{note}".strip() if body else note,
    )
    return int(
        connection.execute("SELECT last_insert_rowid() AS id").fetchone()["id"],
    )


APPLIERS = {
    "create_task": _apply_create_task,
    "notify_user": _apply_notify_user,
    "add_entry": _apply_add_entry,
    "change_stage": _apply_change_stage,
}


def _already_acted_in_window(
    connection: sqlite3.Connection,
    rule: dict[str, Any],
    opportunity: sqlite3.Row,
) -> str | None:
    """Whether a `close_date_approaching` rule has already acted on this deal
    inside its own window.

    **The rule that makes a timer bearable** (milestone 6.5, **D-182**), and
    it applies to exactly one trigger, which is the part worth explaining.

    `no_activity` needs nothing: every action writes a system entry
    (§11's traceability requirement), and that entry *is* activity on the
    deal -- so a nudged deal stops being silent and the rule cannot fire
    again until another full window of silence has passed. The trigger rate
    limits itself, and the behaviour that falls out is the one a person would
    ask for: a quiet deal is chased once per quiet spell.

    `close_date_approaching` has no such feedback. The entry it writes does
    not move the close date, so without this the rule would act on every tick
    for the whole window -- 96 times a day at the shipped interval. Its own
    `days` is the natural unit: once per deal per window, which reads as "you
    have been told".

    Only *applied, non-dry* runs count. A preview must not suppress the real
    run it is previewing, which is the one way to get this subtly wrong.
    """
    if rule["trigger_type"] != "close_date_approaching":
        return None

    days = int(rule["trigger"]["days"])
    acted_at = connection.execute(
        """
        SELECT MAX(created_at) AS acted_at
        FROM automation_runs
        WHERE rule_id = ?
            AND opportunity_id = ?
            AND outcome = 'applied'
            AND dry_run = 0
            AND created_at >= ?
        """,
        (rule["id"], opportunity["id"], utc_days_ago(days)),
    ).fetchone()["acted_at"]
    if acted_at is None:
        return None
    return f"already acted on {acted_at}, within this rule's {days}-day window"


def _would_change_nothing(rule: dict[str, Any], opportunity: sqlite3.Row) -> str | None:
    """The one action that can be asked for and already be true.

    A rule moving a deal to the stage it is already in would otherwise write a
    `stage_change` entry on every run saying nothing changed -- the server's
    half of D-114, applied to a writer that fires on a timer rather than on a
    keystroke.
    """
    if rule["action_type"] == "change_stage" and opportunity["stage"] == rule["action"]["stage"]:
        return f"already in {rule['action']['stage']}"
    return None


# --- The evaluator ----------------------------------------------------------


def _record_run(
    connection: sqlite3.Connection,
    rule_id: int,
    opportunity_id: int,
    outcome: AutomationOutcome,
    reason: str | None,
    entry_id: int | None,
    dry_run: bool,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO automation_runs (
            rule_id, opportunity_id, outcome, reason, entry_id, dry_run, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rule_id,
            opportunity_id,
            outcome,
            reason,
            entry_id,
            int(dry_run),
            utc_now(),
        ),
    )
    return int(cursor.lastrowid or 0)


def _evaluate_one(
    connection: sqlite3.Connection,
    rule: dict[str, Any],
    opportunity: sqlite3.Row,
    definitions: list[dict[str, Any]],
    dry_run: bool,
) -> int | None:
    """One rule against one deal. Returns the run row's id, or `None` when the
    rule simply did not match.

    A non-match is not logged. A rule asked about four hundred deals would
    otherwise write four hundred rows a tick saying nothing happened, and the
    log exists to answer "why did that happen" and "why did that *not*
    happen when it should have" -- the second of which is about a deal that
    matched and was then declined, which is logged.
    """
    unmatched = _matches(opportunity, rule["conditions"], definitions)
    if unmatched is not None:
        return None

    role = get_opportunity_role(connection, int(opportunity["id"]), int(rule["created_by"]))
    if role is None or role not in ACTION_REQUIRES[rule["action_type"]]:
        # Access can have been revoked since the rule was written, and a rule
        # created by an editor can name an owner-only action. Both are a skip
        # with the reason, never a write: a rule may not do what its author
        # could not do by hand (D-173).
        return _record_run(
            connection,
            rule["id"],
            int(opportunity["id"]),
            "skipped",
            f"{rule['creator_name']} may not {rule['action_type'].replace('_', ' ')} here",
            None,
            dry_run,
        )

    repeated = _already_acted_in_window(connection, rule, opportunity)
    if repeated is not None:
        return _record_run(
            connection,
            rule["id"],
            int(opportunity["id"]),
            "skipped",
            repeated,
            None,
            dry_run,
        )

    settled = _would_change_nothing(rule, opportunity)
    if settled is not None:
        return _record_run(
            connection,
            rule["id"],
            int(opportunity["id"]),
            "skipped",
            settled,
            None,
            dry_run,
        )

    if dry_run:
        return _record_run(
            connection,
            rule["id"],
            int(opportunity["id"]),
            "applied",
            "preview only; nothing was written",
            None,
            True,
        )

    reason, entry_id = APPLIERS[rule["action_type"]](
        connection, rule, opportunity, int(rule["created_by"])
    )
    return _record_run(
        connection,
        rule["id"],
        int(opportunity["id"]),
        "applied",
        reason,
        entry_id,
        False,
    )


def run_rule(
    connection: sqlite3.Connection,
    rule: dict[str, Any],
    dry_run: bool,
) -> tuple[int, list[int]]:
    """Evaluate one rule over everything it applies to. Returns
    `(considered, run row ids)`.

    This is the entry point for the two time-driven triggers and for running
    any rule by hand, which is how §11's "always dry-runnable" is satisfied
    for every trigger including the event-driven ones: a rule watching stage
    changes can be previewed against the deals that already satisfy its
    conditions, which is the question somebody writing it is actually asking.
    """
    creator_id = int(rule["created_by"])
    days = rule["trigger"].get("days")
    if rule["trigger_type"] == "no_activity":
        candidates = _no_activity_candidates(connection, creator_id, int(days))
    elif rule["trigger_type"] == "close_date_approaching":
        candidates = _close_date_candidates(connection, creator_id, int(days))
    else:
        candidates = _all_candidates(connection, creator_id)

    # Read once and passed down, not looked up per row -- the shape
    # `opportunity_from_row` and `attachments_by_entry_id` already use for a
    # page of rows (milestone 6.1).
    definitions = live_definitions(connection, "opportunity")
    run_ids = [
        run_id
        for candidate in candidates
        if (run_id := _evaluate_one(connection, rule, candidate, definitions, dry_run)) is not None
    ]
    return len(candidates), run_ids


def _all_candidates(connection: sqlite3.Connection, creator_id: int) -> list[sqlite3.Row]:
    """Every deal the creator can read, for previewing an event-driven rule.

    Closed deals are *not* excluded here, unlike the two time-driven
    selections: a rule triggered by a stage change may legitimately be about
    reaching Closed Won, and this set is "what your conditions currently
    match" rather than "what is stalled".
    """
    clause, params = _accessible_clause(creator_id)
    return list(
        connection.execute(
            f"""
            SELECT {OPPORTUNITY_COLUMNS}
            FROM opportunities
            WHERE {clause}
            ORDER BY opportunities.id
            LIMIT ?
            """,
            (*params, AUTOMATION_RUN_LIMIT),
        ).fetchall()
    )


EventKind = Literal["stage_changed", "entry_created", "field_changed"]

# The two of §11's five triggers the clock owns rather than a human write.
# `jobs.run_automations` reads this to decide what a tick evaluates (milestone
# 6.5): the other three are fired by `fire_event_after_commit` below, from the
# route that performed the write, so a tick walking them as well would act on
# every matching deal every fifteen minutes.
TIME_TRIGGERS: tuple[str, ...] = ("no_activity", "close_date_approaching")


def fire_event(
    connection: sqlite3.Connection,
    trigger: EventKind,
    opportunity_id: int,
    event: dict[str, Any],
) -> list[int]:
    """Every armed rule watching this trigger, against the deal it happened on.

    Called from a route handler **below its commit**, on a fresh connection,
    for the reason `publish_*` is (ADR 0003): the work here is a second
    transaction, and a reader refetching because of it must not be sent to
    read state the first one is about to replace.

    **Nothing in this module calls it** (D-174), which is the whole of §11's
    "no rule may trigger another rule": the writes above are
    `system_generated` and reach no trigger, and a rule's action therefore
    cannot wake a rule. One hop, with no loop detection anywhere.
    """
    rules = connection.execute(
        f"""
        {RULE_ROWS_SQL}
        WHERE automation_rules.trigger_type = ?
            AND automation_rules.archived_at IS NULL
            AND automation_rules.enabled = 1
        ORDER BY automation_rules.id
        """,
        (trigger,),
    ).fetchall()

    definitions = live_definitions(connection, "opportunity")
    run_ids: list[int] = []
    for row in rules:
        rule = rule_from_row(row)
        if _trigger_wants(rule, event) is not None:
            continue
        for candidate in _event_candidates(connection, int(rule["created_by"]), opportunity_id):
            run_id = _evaluate_one(connection, rule, candidate, definitions, dry_run=False)
            if run_id is not None:
                run_ids.append(run_id)
    return run_ids


def fire_event_after_commit(
    trigger: EventKind,
    opportunity_id: int,
    event: dict[str, Any],
) -> list[int]:
    """`fire_event` on its own connection, for a route to call below its commit.

    Three things are bundled here so a call site is one line and cannot get
    any of them wrong:

    - **Its own connection**, because the caller's has already committed and
      `database.py` opens one per operation rather than pooling.
    - **Published afterwards, and only if something was written.** The route
      has already published its own invalidation for the human write; this is
      a second, later write, so a subscriber refetching on the first event
      would read the state this one is about to replace -- the same ordering
      argument ADR 0003 makes for publishing below the commit.
    - **Nothing bubbles up.** A rule that fails must not fail the request that
      triggered it: the person renamed a deal, and whether somebody else's
      automation managed to act on that is not their problem. The run is
      recorded as `failed` with the reason, which is the log's job.
    """
    try:
        with db_connection() as connection:
            run_ids = fire_event(connection, trigger, opportunity_id, event)
            connection.commit()
    except sqlite3.Error as exc:
        logger.warning(
            "automation_event_failed",
            extra={"trigger": trigger, "opportunity_id": opportunity_id, "error": str(exc)},
        )
        return []
    if run_ids:
        publish_opportunity_changed(opportunity_id)
    return run_ids


def automation_rule_ids_by_entry_id(
    connection: sqlite3.Connection,
    entry_ids: list[int],
) -> dict[int, int]:
    """Which rule wrote each of these entries, for the ones a rule wrote.

    One query for a whole page, the shape `attachments_by_entry_id` already
    uses (milestone 6.3a). Read for the permission the entry card offers: the
    deal's owner may delete an entry a rule wrote (**D-181**), and no other
    system entry.

    `MIN(rule_id)` rather than a bare `rule_id`: an entry is written by exactly
    one run today, and grouping says so in SQL rather than relying on it --
    the alternative is a query that silently returns two rows per entry if
    that ever stops being true.
    """
    if not entry_ids:
        return {}
    placeholders = ",".join("?" for _ in entry_ids)
    rows = connection.execute(
        f"""
        SELECT entry_id, MIN(rule_id) AS rule_id
        FROM automation_runs
        WHERE entry_id IN ({placeholders})
        GROUP BY entry_id
        """,
        entry_ids,
    ).fetchall()
    return {int(row["entry_id"]): int(row["rule_id"]) for row in rows}
