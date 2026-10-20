"""Automation rules: write one, preview it, run it, read what it did.

Milestone 6.3, `docs/FEATURES.md` §11. Like a custom field definition and a
saved view, a rule is **not opportunity-scoped**, so `permissions.py`'s
owner/editor/viewer machinery does not gate these routes -- it gates what the
rule may *do*, per deal, inside `automations.py`.

**Who may write a rule is D-173**, and it is two rules rather than one:

- **Creating one is open to any authenticated caller**, as a custom field
  definition is (D-171). The argument is different and stronger here: a rule
  acts with its creator's authority, over the deals its creator can already
  read, performing only actions its creator's role allows. So a rule grants
  nobody anything they did not have, and gating creation would only decide who
  gets the convenience.
- **Editing, archiving and running one is the creator's alone.** This is where
  it departs from custom fields, which anybody may edit: a field's label is
  read by everyone and a typo in it should be fixable by whoever notices,
  while a rule performs *writes attributed to its creator*. Changing somebody
  else's rule changes what their name will be recorded as having done, which
  is not a thing to leave open. Reading the list stays open, because "what
  automations run here" is a question everybody on a shared deal has a stake
  in -- and a rule carries conditions, not anybody's data.

The 404-rather-than-403 convention does not apply: these rows are not
opportunity-scoped, so a rule's existence leaks nothing about a deal. A rule
somebody else owns answers **403** on a write, the way `routes_sharing.py`'s
owner-only endpoints answer a shared editor (D-007's reasoning: "you can see
this, but cannot do that").
"""

import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .auth import get_current_user
from .automations import (
    RULE_ROWS_SQL,
    RUN_ROWS_SQL,
    rule_from_row,
    run_from_row,
    run_rule,
)
from .database import db_connection
from .events import publish_opportunity_changed
from .jobs import JOB_ROWS_SQL, job_run_from_row
from .pagination import Page, PageRequest, cursor_clause, page_params, split_page
from .permissions import require_admin
from .schemas import (
    MAX_ENABLED_RULES_PER_CREATOR,
    AutomationRuleCreate,
    AutomationRulePublic,
    AutomationRuleUpdate,
    AutomationRunPublic,
    AutomationRunResponse,
    JobRunPublic,
)
from .time_utils import utc_now

router = APIRouter(prefix="/api/v2/automation-rules", tags=["automations"])
# The scheduler's log is not a rule's, so it gets its own path rather than
# living under `/automation-rules/jobs/...` -- which would also be matched by
# `/{rule_id}/runs` first, since FastAPI resolves in declaration order and
# `jobs` is not an integer.
jobs_router = APIRouter(prefix="/api/v2/job-runs", tags=["automations"])


def rule_public(row: sqlite3.Row) -> AutomationRulePublic:
    return AutomationRulePublic(**rule_from_row(row))


def fetch_rule(connection: sqlite3.Connection, rule_id: int) -> sqlite3.Row:
    row: sqlite3.Row | None = connection.execute(
        f"{RULE_ROWS_SQL} WHERE automation_rules.id = ?",
        (rule_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Automation rule not found",
        )
    return row


def require_rule_creator(row: sqlite3.Row, user_id: int) -> None:
    if int(row["created_by"]) != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the rule's creator can change or run it",
        )


def refuse_over_the_cap(connection: sqlite3.Connection, user_id: int) -> None:
    """§11's "capped in number", counted per creator (D-173).

    Only enabled rules count, so somebody experimenting can keep a shelf of
    disabled ones; and the count is taken before the write rather than
    enforced by a constraint, because "at most twenty" is not a thing a unique
    index can say.
    """
    live = connection.execute(
        """
        SELECT COUNT(*) AS total FROM automation_rules
        WHERE created_by = ? AND archived_at IS NULL AND enabled = 1
        """,
        (user_id,),
    ).fetchone()["total"]
    if live >= MAX_ENABLED_RULES_PER_CREATOR:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"You already have {MAX_ENABLED_RULES_PER_CREATOR} enabled rules; "
                "disable or archive one first"
            ),
        )


@router.get("", response_model=Page[AutomationRulePublic])
def list_automation_rules(
    include_archived: bool = Query(default=False),
    mine_only: bool = Query(default=False),
    page: PageRequest = Depends(page_params),
    user: sqlite3.Row = Depends(get_current_user),
) -> Page[AutomationRulePublic]:
    """Every rule, or only the caller's.

    Open to any authenticated caller, and the creator is named on each row --
    a reader who finds a stage changing under them should be able to see which
    rule did it and whose it is. `mine_only` is what the builder's own screen
    asks for, since those are the rules this caller can actually edit.
    """
    filters = ["1 = 1"]
    params: list[object] = []
    if not include_archived:
        filters.append("automation_rules.archived_at IS NULL")
    if mine_only:
        filters.append("automation_rules.created_by = ?")
        params.append(int(user["id"]))

    continuation, cursor_values = cursor_clause(
        page,
        "automation_rules.created_at",
        "automation_rules.id",
        descending=False,
    )
    if continuation:
        filters.append(continuation)
        params.extend(cursor_values)

    with db_connection() as connection:
        rows = connection.execute(
            f"""
            {RULE_ROWS_SQL}
            WHERE {" AND ".join(filters)}
            ORDER BY automation_rules.created_at, automation_rules.id
            LIMIT ?
            """,
            (*params, page.limit + 1),
        ).fetchall()

    rows, next_cursor = split_page(rows, page.limit, lambda row: (row["created_at"], row["id"]))
    return Page(items=[rule_public(row) for row in rows], next_cursor=next_cursor)


@router.post("", response_model=AutomationRulePublic, status_code=status.HTTP_201_CREATED)
def create_automation_rule(
    payload: AutomationRuleCreate,
    user: sqlite3.Row = Depends(get_current_user),
) -> AutomationRulePublic:
    """Write a rule. **Administrators only since R.1c** (**D-215**).

    D-173 left this open to any authenticated caller, on the reasoning that a
    rule grants its author nothing they did not already have: it is evaluated
    only over deals its creator can read, attributed to them, and the role
    each action needs is re-checked per deal at run time. That reasoning
    still holds -- and the reviewer ruled anyway, at the Phase R gate:
    *"both have to be done by the owner."* The distinction they were drawing
    is the one D-173 itself named: a rule **writes to records** rather than to
    metadata, unattended, under somebody's name. Who may set that in motion is
    a narrower question than who may be trusted with their own authority.

    Everything else about a rule is unchanged, including that editing,
    archiving and running one stays the creator's alone -- an admin does not
    inherit another admin's rules.
    """
    require_admin(user)
    with db_connection() as connection:
        if payload.enabled:
            refuse_over_the_cap(connection, int(user["id"]))
        now = utc_now()
        cursor = connection.execute(
            """
            INSERT INTO automation_rules (
                name, trigger_type, trigger_config, conditions,
                action_type, action_config, enabled, created_by,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.name,
                payload.trigger_type,
                payload.trigger.model_dump_json(exclude_none=True),
                json.dumps([condition.model_dump() for condition in payload.conditions]),
                payload.action_type,
                payload.action.model_dump_json(exclude_none=True),
                int(payload.enabled),
                int(user["id"]),
                now,
                now,
            ),
        )
        connection.commit()
        return rule_public(fetch_rule(connection, int(cursor.lastrowid or 0)))


@router.patch("/{rule_id}", response_model=AutomationRulePublic)
def update_automation_rule(
    rule_id: int,
    payload: AutomationRuleUpdate,
    user: sqlite3.Row = Depends(get_current_user),
) -> AutomationRulePublic:
    """Rewrite a rule whole. The creator's alone (D-173)."""
    with db_connection() as connection:
        row = fetch_rule(connection, rule_id)
        require_rule_creator(row, int(user["id"]))
        if row["archived_at"] is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An archived rule cannot be edited; create a new one",
            )
        if payload.enabled and not row["enabled"]:
            refuse_over_the_cap(connection, int(user["id"]))

        connection.execute(
            """
            UPDATE automation_rules
            SET name = ?, trigger_type = ?, trigger_config = ?, conditions = ?,
                action_type = ?, action_config = ?, enabled = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                payload.name,
                payload.trigger_type,
                payload.trigger.model_dump_json(exclude_none=True),
                json.dumps([condition.model_dump() for condition in payload.conditions]),
                payload.action_type,
                payload.action.model_dump_json(exclude_none=True),
                int(payload.enabled),
                utc_now(),
                rule_id,
            ),
        )
        connection.commit()
        return rule_public(fetch_rule(connection, rule_id))


@router.post("/{rule_id}/archive", response_model=AutomationRulePublic)
def archive_automation_rule(
    rule_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> AutomationRulePublic:
    """Retire a rule without losing what it did.

    There is no DELETE: `automation_runs.rule_id` points here, and a log
    saying "rule 4 changed this deal's stage" is worthless if rule 4 can
    vanish. Idempotent, like `archive_custom_field` -- the first archiver is
    the one recorded and a retry is safe.
    """
    with db_connection() as connection:
        row = fetch_rule(connection, rule_id)
        require_rule_creator(row, int(user["id"]))
        if row["archived_at"] is None:
            now = utc_now()
            connection.execute(
                """
                UPDATE automation_rules
                SET archived_at = ?, enabled = 0, updated_at = ?
                WHERE id = ?
                """,
                (now, now, rule_id),
            )
            connection.commit()
            row = fetch_rule(connection, rule_id)
        return rule_public(row)


@router.post("/{rule_id}/run", response_model=AutomationRunResponse)
def run_automation_rule(
    rule_id: int,
    dry_run: bool = Query(default=True),
    user: sqlite3.Row = Depends(get_current_user),
) -> AutomationRunResponse:
    """§11's "always dry-runnable", and the manual half of "run it now".

    **`dry_run` defaults to true**, which is the one place in this API a
    default decides whether anything is written. It is deliberate: a preview
    is what somebody writing a rule wants nine times out of ten, and the
    failure mode of the other default is a rule applied to two hundred deals
    by somebody who meant to look first.

    An archived rule can still be previewed and cannot be applied -- the
    reason to keep the row at all is to answer questions about it.

    This is also the route milestone 6.5's scheduler replaces for the two
    time-driven triggers. It calls `run_rule`, not this handler: a scheduled
    tick has no caller to authorize, and the authority it runs with is the
    rule creator's either way.
    """
    with db_connection() as connection:
        row = fetch_rule(connection, rule_id)
        require_rule_creator(row, int(user["id"]))
        if row["archived_at"] is not None and not dry_run:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An archived rule cannot be applied",
            )
        rule = rule_from_row(row)
        considered, run_ids = run_rule(connection, rule, dry_run=dry_run)
        connection.commit()
        runs = [run_from_row(fetch_run(connection, run_id)) for run_id in run_ids]

    # Only an applied run changed anything, and it may have touched several
    # deals -- so the invalidation is published per opportunity, below the
    # commit, the way every other write in this app publishes (ADR 0003).
    if not dry_run:
        for opportunity_id in dict.fromkeys(run.opportunity_id for run in runs):
            publish_opportunity_changed(opportunity_id)
    return AutomationRunResponse(dry_run=dry_run, considered=considered, runs=runs)


def fetch_run(connection: sqlite3.Connection, run_id: int) -> sqlite3.Row:
    row: sqlite3.Row | None = connection.execute(
        f"{RUN_ROWS_SQL} WHERE automation_runs.id = ?",
        (run_id,),
    ).fetchone()
    assert row is not None
    return row


@router.get("/{rule_id}/runs", response_model=Page[AutomationRunPublic])
def list_automation_runs(
    rule_id: int,
    page: PageRequest = Depends(page_params),
    user: sqlite3.Row = Depends(get_current_user),
) -> Page[AutomationRunPublic]:
    """What this rule has done, newest last.

    Oldest-first and keyset-paginated, for the reason the audit log and the
    activity feed are: a log is read in the order it happened. The creator's
    alone, like every other read of a rule's behaviour -- a run row names a
    deal, so this is the one place in these routes where the rows could carry
    something the caller may not be able to read otherwise.
    """
    with db_connection() as connection:
        row = fetch_rule(connection, rule_id)
        require_rule_creator(row, int(user["id"]))

        filters = ["automation_runs.rule_id = ?"]
        params: list[object] = [rule_id]
        continuation, cursor_values = cursor_clause(
            page,
            "automation_runs.created_at",
            "automation_runs.id",
            descending=False,
        )
        if continuation:
            filters.append(continuation)
            params.extend(cursor_values)

        rows = connection.execute(
            f"""
            {RUN_ROWS_SQL}
            WHERE {" AND ".join(filters)}
            ORDER BY automation_runs.created_at, automation_runs.id
            LIMIT ?
            """,
            (*params, page.limit + 1),
        ).fetchall()

    rows, next_cursor = split_page(rows, page.limit, lambda row: (row["created_at"], row["id"]))
    return Page(items=[run_from_row(row) for row in rows], next_cursor=next_cursor)


@jobs_router.get("", response_model=Page[JobRunPublic])
def list_job_runs(
    page: PageRequest = Depends(page_params),
    user: sqlite3.Row = Depends(get_current_user),
) -> Page[JobRunPublic]:
    """The scheduler's own log, newest first (milestone 6.5, ADR 0004).

    Read by the automations screen, which says when the rules were last
    checked -- the question somebody wondering why a rule has not fired
    actually has. The backup's runs are in the same log because they come from
    the same scheduler, and a reader asking "is anything running at all"
    wants both.

    **Newest first**, unlike every other paginated read here. The others are
    histories read forwards from a beginning; this one is read from the
    present backwards, because "when did it last run" is the whole question.
    Open to any authenticated caller: a job name, a status and a time say
    nothing about anybody's deals (**D-183**).
    """
    filters = ["1 = 1"]
    params: list[object] = []
    continuation, cursor_values = cursor_clause(
        page,
        "job_runs.started_at",
        "job_runs.id",
        descending=True,
    )
    if continuation:
        filters.append(continuation)
        params.extend(cursor_values)

    with db_connection() as connection:
        rows = connection.execute(
            f"""
            {JOB_ROWS_SQL}
            WHERE {" AND ".join(filters)}
            ORDER BY job_runs.started_at DESC, job_runs.id DESC
            LIMIT ?
            """,
            (*params, page.limit + 1),
        ).fetchall()

    rows, next_cursor = split_page(rows, page.limit, lambda row: (row["started_at"], row["id"]))
    return Page(items=[job_run_from_row(row) for row in rows], next_cursor=next_cursor)
