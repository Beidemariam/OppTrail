"""Tasks scoped to an opportunity (milestone 4.1, `docs/FEATURES.md` §8).

"Call them back Thursday" is the most common output of a sales conversation and
had nowhere to live except prose. A task is an action item on one deal: a title,
somebody to do it, a date it is due, whether it is done, and optionally the
entry that prompted it.

Four things about this file are decisions rather than mechanics:

- **Completing is not editing** (**D-142**). `PATCH` changes what a person
  typed and is limited to the author or the opportunity owner, the rule every
  existing item follows (D-005). **Ticking a task off is also open to its
  assignee**, because handing somebody a task and then refusing to let them
  close it is not a permission model, it is a bug. `require_task_completion`
  below is the only place in this app where a row's own column widens who may
  change it, which is why it is spelled out rather than folded into
  `permissions.py`'s general helpers.
- **Done state is `POST .../complete` and `.../reopen`**, not a `PATCH` field —
  the shape resolving a comment thread already uses (D-128). Both are
  idempotent through `COALESCE`, so the first completer is the one recorded and
  a double click is not a second event.
- **An assignee is named by email**, resolved here. Naming somebody nobody has
  heard of is a 422 about the request rather than a task quietly left
  unassigned, which is the same answer `POST /opportunities/bulk`'s
  `assign_owner` gives (3.0a).
- **My Tasks is the one read that spans opportunities**, so its permission
  filter is inside the query (`ACCESSIBLE_OPPORTUNITY_IDS_SQL`) rather than a
  role resolved first -- the pattern `search.py` established and
  `/timeline/follow-ups` followed.
"""

import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .audit_utils import create_audit_log_entry
from .auth import get_current_user
from .database import db_connection
from .events import publish_opportunity_changed
from .notification_service import create_notification
from .pagination import Page, PageRequest, cursor_clause, page_params, split_page
from .permissions import (
    ACCESSIBLE_OPPORTUNITY_IDS_SQL,
    require_delete_permission,
    require_edit_permission,
    require_opportunity_access,
    require_opportunity_owner,
    require_timeline_write,
)
from .schemas import (
    TaskAssigneePublic,
    TaskCommentCreate,
    TaskCommentPublic,
    TaskCreate,
    TaskPublic,
    TaskUpdate,
    TaskVersionPublic,
)
from .soft_delete import (
    restore_task,
    restore_task_comment,
    soft_delete_task,
    soft_delete_task_comment,
)
from .time_utils import utc_now
from .versioning import (
    TASK_VERSIONS,
    apply_version,
    fetch_version,
    record_version,
    version_is_current,
)

router = APIRouter(prefix="/api/v2", tags=["tasks"])

# Every read of a task answers with the deal it belongs to and the people on it,
# because My Tasks shows tasks from several opportunities at once and a bare
# title is not actionable. Shared for the reason `ENTRY_ROWS_SQL` is: five reads
# answer with a task and a client cannot tell which one produced the row.
# `assignee_ids` is the canonical form of the set: ids ascending, comma
# separated, NULL for nobody. Canonical because `task_versions` snapshots this
# exact string and `versioning.version_is_current` compares two of them
# (milestone 4.6) -- SQLite's `group_concat` has no ordering of its own, so the
# order comes from the subquery. `assignee_names` is the same set for reading,
# in the same order, so the two never disagree about who is on a task.
TASK_ROWS_SQL = """
    SELECT
        tasks.*,
        opportunities.name AS opportunity_name,
        timeline_entries.title AS entry_title,
        authors.name AS author_name,
        completers.name AS completed_by_name,
        (
            SELECT group_concat(user_id)
            FROM (
                SELECT user_id FROM task_assignees
                WHERE task_assignees.task_id = tasks.id
                ORDER BY user_id
            )
        ) AS assignee_ids,
        (
            SELECT group_concat(name, char(31))
            FROM (
                SELECT users.name AS name
                FROM task_assignees
                JOIN users ON users.id = task_assignees.user_id
                WHERE task_assignees.task_id = tasks.id
                ORDER BY task_assignees.user_id
            )
        ) AS assignee_names
    FROM tasks
    JOIN opportunities ON opportunities.id = tasks.opportunity_id
    LEFT JOIN timeline_entries
        ON timeline_entries.id = tasks.entry_id
        AND timeline_entries.deleted_at IS NULL
    LEFT JOIN users AS authors ON authors.id = tasks.created_by
    LEFT JOIN users AS completers ON completers.id = tasks.completed_by
"""

# `group_concat`'s separator for names: a name can contain a comma ("Osei,
# Blair") and cannot contain a control character, so the two lists are split on
# different things on purpose.
NAME_SEPARATOR = chr(31)


def assignee_ids_of(row: sqlite3.Row) -> list[int]:
    """The set a task row carries, as ids. Empty when nobody is on it."""
    raw = row["assignee_ids"]
    return [int(value) for value in raw.split(",")] if raw else []


def version_assignees(row: sqlite3.Row) -> list[TaskAssigneePublic]:
    """The people a recorded version was assigned to (milestone 4.6).

    Its own function rather than `assignees_of`, because the two read different
    columns: a task row carries the set from `task_assignees`, a version row
    carries the snapshot string and joins the names to it. The commas on both
    sides of the `instr` match are what stop id `3` matching `13`.
    """
    raw = row["assignee_ids"]
    ids = sorted(int(value) for value in raw.split(",")) if raw else []
    names = row["assignee_names"].split(NAME_SEPARATOR) if row["assignee_names"] else []
    return [
        TaskAssigneePublic(user_id=user_id, name=name)
        for user_id, name in zip(ids, names, strict=False)
    ]


def assignees_of(row: sqlite3.Row) -> list[TaskAssigneePublic]:
    ids = assignee_ids_of(row)
    names = row["assignee_names"].split(NAME_SEPARATOR) if row["assignee_names"] else []
    return [
        TaskAssigneePublic(user_id=user_id, name=name)
        for user_id, name in zip(ids, names, strict=True)
    ]


TASK_COMMENT_ROWS_SQL = """
    SELECT task_comments.*, users.name AS author_name
    FROM task_comments
    JOIN users ON users.id = task_comments.created_by
"""


def task_comment_from_row(row: sqlite3.Row) -> TaskCommentPublic:
    return TaskCommentPublic(
        id=row["id"],
        task_id=row["task_id"],
        body=row["body"],
        created_by=row["created_by"],
        author_name=row["author_name"],
        created_at=row["created_at"],
    )


def comments_by_task_id(
    connection: sqlite3.Connection,
    task_ids: list[int],
) -> dict[int, list[TaskCommentPublic]]:
    """Every comment on the given tasks, one query for the whole set
    (milestone 4.5) -- the shape `attachments_by_entry_id` and
    `reactions_by_comment_id` already use, so a page of tasks costs one more
    round trip rather than one per row."""
    if not task_ids:
        return {}
    placeholders = ",".join("?" for _ in task_ids)
    rows = connection.execute(
        f"""
        {TASK_COMMENT_ROWS_SQL}
        WHERE task_comments.deleted_at IS NULL
            AND task_comments.task_id IN ({placeholders})
        ORDER BY task_comments.created_at ASC, task_comments.id ASC
        """,
        task_ids,
    ).fetchall()
    grouped: dict[int, list[TaskCommentPublic]] = {}
    for row in rows:
        grouped.setdefault(row["task_id"], []).append(task_comment_from_row(row))
    return grouped


def task_from_row(
    row: sqlite3.Row,
    comments: list[TaskCommentPublic] | None = None,
) -> TaskPublic:
    return TaskPublic(
        id=row["id"],
        opportunity_id=row["opportunity_id"],
        opportunity_name=row["opportunity_name"],
        entry_id=row["entry_id"],
        # `NULL` when the entry it came from has been deleted, which is
        # deliberate: an action item outlives the record of where it came from.
        entry_title=row["entry_title"],
        title=row["title"],
        description=row["description"],
        # A list since milestone 4.6, and no `assignee_id` beside it: two
        # shapes for one fact is how a client comes to believe the wrong one.
        assignees=assignees_of(row),
        due_date=row["due_date"],
        completed_at=row["completed_at"],
        completed_by=row["completed_by"],
        completed_by_name=row["completed_by_name"],
        created_by=row["created_by"],
        author_name=row["author_name"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        # Defaulted rather than required, because the six writes that answer
        # with a task answer with the row they changed and the client refetches
        # -- the same thing `entry_from_row` does with an entry's notes. Only
        # the two reads that draw a list fill it.
        comments=comments or [],
    )


def fetch_task(connection: sqlite3.Connection, task_id: int) -> sqlite3.Row:
    """One live task, or 404. The opportunity's own `deleted_at` is checked too:
    deleting a deal takes its tasks with it (`soft_delete.py`), so a task whose
    deal is gone is not reachable even if this row were somehow still live."""
    # Annotated so the `None` check below narrows it: `fetchone()` is typed
    # `Any`, and returning that as a `Row` is what mypy's `no-any-return`
    # objects to.
    row: sqlite3.Row | None = connection.execute(
        f"""
        {TASK_ROWS_SQL}
        WHERE tasks.id = ?
            AND tasks.deleted_at IS NULL
            AND opportunities.deleted_at IS NULL
        """,
        (task_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return row


def notify_assigned(
    connection: sqlite3.Connection,
    *,
    opportunity_id: int,
    actor_id: int,
    task_id: int,
    title: str,
    due_date: str | None,
    user_ids: list[int],
) -> None:
    """Tell each person they were handed this, once, and never the person doing
    the handing (milestone 4.6 made it a loop; the rule is 4.1's)."""
    for user_id in sorted(set(user_ids)):
        if user_id == actor_id:
            continue
        create_notification(
            connection,
            user_id,
            "task_assigned",
            {
                "opportunity_id": opportunity_id,
                "actor_id": actor_id,
                "task_id": task_id,
                "title": title,
                "due_date": due_date,
            },
        )


def set_assignees(connection: sqlite3.Connection, task_id: int, user_ids: list[int]) -> None:
    """Make `task_assignees` say exactly this (milestone 4.6).

    Written as a replacement rather than a diff: the request carries the whole
    list, so working out what to add and what to remove here would be deriving
    something the caller already knows. The delete is an ordinary `DELETE FROM`
    and is meant to be -- an assignment is "this person owes this now", the
    toggle state `soft_delete.py` keeps out of `USER_DATA_TABLES` for the same
    reason it keeps `reactions` and `watchers` out (**D-130**). Who *used* to
    owe it is in `task_versions`, which is the history that matters.
    """
    connection.execute("DELETE FROM task_assignees WHERE task_id = ?", (task_id,))
    now = utc_now()
    for user_id in sorted(set(user_ids)):
        connection.execute(
            "INSERT INTO task_assignees (task_id, user_id, created_at) VALUES (?, ?, ?)",
            (task_id, user_id, now),
        )


def resolve_assignees(connection: sqlite3.Connection, emails: list[str]) -> list[int]:
    """Emails to user ids, or 422 naming the first address nobody uses.

    One query rather than one per address, and the refusal is about the request
    rather than about one field -- so a list with one bad address in it writes
    nothing at all, which is the answer `assign_owner` gives (3.0a).
    """
    wanted = list(dict.fromkeys(email.strip() for email in emails if email.strip()))
    if not wanted:
        return []
    placeholders = ",".join("?" for _ in wanted)
    rows = connection.execute(
        f"SELECT id, email FROM users WHERE email IN ({placeholders})",
        wanted,
    ).fetchall()
    found = {row["email"]: int(row["id"]) for row in rows}
    for email in wanted:
        if email not in found:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"No user with email {email}",
            )
    return [found[email] for email in wanted]


def resolve_assignee(connection: sqlite3.Connection, email: str) -> int:
    """An email to a user id, or 422.

    Wrong about the request rather than about one field, so it is raised before
    anything is written -- the same answer `assign_owner` gives for an email
    nobody uses (3.0a). It does not check that the assignee can *see* the deal:
    a task can be written for a colleague before they are shared on it, and
    `POST /shares` is how that is fixed. Widening it to require access would
    make the order of two independent actions matter.
    """
    # `users` carries no `deleted_at`: an account is not deleted in this app
    # (`soft_delete.py` lists the table for the scanner's sake, and nothing
    # writes it), so this is the same lookup `POST /shares` does.
    row = connection.execute(
        "SELECT id FROM users WHERE email = ?",
        (email.strip(),),
    ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"No user with email {email}",
        )
    return int(row["id"])


def require_task_completion(
    connection: sqlite3.Connection,
    task: sqlite3.Row,
    user_id: int,
) -> None:
    """Who may tick a task off: its author, the opportunity owner, or **anyone
    it is assigned to** (**D-142**, read against a set since milestone 4.6).

    The first two are D-005's rule, resolved through the same
    `require_timeline_write` gate every other write uses. The third is the
    addition, and the reason this function exists at all: a task assigned to
    somebody who cannot close it is worse than no task. With more than one
    person on it, "the assignee" became "any of them" -- a shared task is done
    when whoever got to it says so, and asking the other two to agree is a
    workflow this app does not have.
    """
    role = require_timeline_write(connection, int(task["opportunity_id"]), user_id)
    if role == "owner":
        return
    if user_id == task["created_by"] or user_id in assignee_ids_of(task):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only the task's author, assignee or the opportunity owner can change it",
    )


@router.post(
    "/opportunities/{opportunity_id}/tasks",
    response_model=TaskPublic,
    status_code=status.HTTP_201_CREATED,
)
def create_task(
    opportunity_id: int,
    payload: TaskCreate,
    user: sqlite3.Row = Depends(get_current_user),
) -> TaskPublic:
    """Writing a task down. Editors may, viewers may not -- the same gate as
    adding an entry or a note, because this is adding something rather than
    changing somebody else's."""
    with db_connection() as connection:
        require_timeline_write(connection, opportunity_id, int(user["id"]))

        assignee_ids = resolve_assignees(connection, payload.assignee_emails)
        if payload.entry_id is not None:
            # The link must point at an entry on *this* deal. A foreign key
            # cannot say that, so the route does -- the same rule a reply's
            # parent follows (D-127), and a 404 rather than a 400 because an
            # entry on another opportunity is one this caller may not know
            # exists.
            entry = connection.execute(
                """
                SELECT id FROM timeline_entries
                WHERE id = ? AND opportunity_id = ? AND deleted_at IS NULL
                """,
                (payload.entry_id, opportunity_id),
            ).fetchone()
            if entry is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Entry not found on this opportunity",
                )

        now = utc_now()
        cursor = connection.execute(
            """
            INSERT INTO tasks (
                opportunity_id, entry_id, title, description,
                due_date, created_by, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                opportunity_id,
                payload.entry_id,
                payload.title,
                payload.description,
                payload.due_date,
                int(user["id"]),
                now,
                now,
            ),
        )
        task_id = int(cursor.lastrowid or 0)
        # `tasks.assignee_id` is not written here at all since milestone 4.6:
        # the join table is the truth and the column is frozen until Phase 6
        # drops it, so there is no second place for the two to disagree.
        set_assignees(connection, task_id, assignee_ids)

        notify_assigned(
            connection,
            opportunity_id=opportunity_id,
            actor_id=int(user["id"]),
            task_id=task_id,
            title=payload.title,
            due_date=payload.due_date,
            user_ids=assignee_ids,
        )

        row = fetch_task(connection, task_id)
        # Version 1 at creation, so the history opens with what the task said on
        # day one rather than with its first edit (milestone 4.2a, the rule
        # `versioning.py` already applies to the other three).
        record_version(connection, TASK_VERSIONS, task_id, row, int(user["id"]), now)
        connection.commit()

    # A task is not on the timeline, so this is `opportunity.changed`: an
    # invalidation may be broader than the write behind it and never narrower
    # (ADR 0003), and adding a third event type for a list that hangs off the
    # same record would be a second answer to one question (**D-143**).
    publish_opportunity_changed(opportunity_id)
    return task_from_row(row)


@router.get("/opportunities/{opportunity_id}/tasks", response_model=Page[TaskPublic])
def list_tasks(
    opportunity_id: int,
    page: PageRequest = Depends(page_params),
    include_completed: bool = Query(default=True),
    user: sqlite3.Row = Depends(get_current_user),
) -> Page[TaskPublic]:
    """One deal's tasks, soonest first.

    `due_date` is nullable and SQLite sorts `NULL` before every value, so a task
    with no date would otherwise lead the list. `due_date IS NULL` as the first
    sort key puts the undated ones last, where a reader expects them -- and the
    cursor carries the same expression, since a keyset cursor over a different
    order than the one displayed skips rows.
    """
    where = ["tasks.deleted_at IS NULL", "tasks.opportunity_id = ?"]
    params: list[object] = [opportunity_id]
    if not include_completed:
        where.append("tasks.completed_at IS NULL")

    continuation, cursor_values = cursor_clause(
        page,
        "tasks.due_date",
        "tasks.id",
        descending=False,
    )
    if continuation:
        where.append(continuation)
        params.extend(cursor_values)
    params.append(page.limit + 1)

    with db_connection() as connection:
        require_opportunity_access(connection, opportunity_id, int(user["id"]))
        rows = connection.execute(
            f"""
            {TASK_ROWS_SQL}
            WHERE {" AND ".join(where)}
            ORDER BY tasks.due_date IS NULL, tasks.due_date ASC, tasks.id ASC
            LIMIT ?
            """,
            params,
        ).fetchall()

    tasks, next_cursor = split_page(rows, page.limit, lambda row: (row["due_date"], row["id"]))
    with db_connection() as connection:
        comments = comments_by_task_id(connection, [row["id"] for row in tasks])
    return Page(
        items=[task_from_row(row, comments.get(row["id"], [])) for row in tasks],
        next_cursor=next_cursor,
    )


@router.get("/tasks", response_model=Page[TaskPublic])
def list_tasks_across_opportunities(
    page: PageRequest = Depends(page_params),
    include_completed: bool = Query(default=False),
    due_before: str | None = Query(default=None),
    assignee: Literal["me", "any"] = Query(default="me"),
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
    user: sqlite3.Row = Depends(get_current_user),
) -> Page[TaskPublic]:
    """Tasks across every opportunity the caller can still see.

    Two readers, one query. `assignee=me` is the default and is **My Tasks** --
    what this reader owes. `assignee=any` is the calendar's follow-up layer
    (milestone 4.2), which draws every outstanding task on a visible deal
    whoever it belongs to, because that is what the `follow_up_date` layer it
    replaces did (3.0b, D-088). One route with a filter rather than two routes
    over the same rows: the permission rule, the ordering and the cursor are
    identical, and the only difference is one `WHERE` clause.

    `from`/`to` bound it to the month on screen, the same parameter names the
    timeline's own filter uses -- here they filter `due_date`.

    The one read here that spans opportunities, so the permission filter is
    inside the query rather than a role resolved first -- `search.py`'s pattern.
    A page of 50 is 50 tasks on deals this reader may read, which matters
    because a task can be assigned to somebody before they are shared on the
    deal: the share going away takes the task off their list rather than leaking
    the deal's name through it.

    Open by default, because a list of everything you have ever finished is not
    a to-do list. `due_before` is what the dashboard's overdue surface asks for.
    """
    where = [
        "tasks.deleted_at IS NULL",
        "opportunities.deleted_at IS NULL",
        f"tasks.opportunity_id IN ({ACCESSIBLE_OPPORTUNITY_IDS_SQL})",
    ]
    # Params follow the order the clauses appear in, not the order they are
    # decided: `ACCESSIBLE_OPPORTUNITY_IDS_SQL` is the third clause and carries
    # two of its own, so the assignee's placeholder is bound after them.
    params: list[object] = [int(user["id"]), int(user["id"])]
    if assignee == "me":
        # A membership test since milestone 4.6, served by
        # `idx_task_assignees_user`: "what do I owe" reads the join table the
        # other way round from "who is on this task".
        where.append(
            "EXISTS (SELECT 1 FROM task_assignees "
            "WHERE task_assignees.task_id = tasks.id AND task_assignees.user_id = ?)"
        )
        params.append(int(user["id"]))
    if not include_completed:
        where.append("tasks.completed_at IS NULL")
    if due_before:
        # An overdue task always has a date, so this filters the undated ones
        # out on its own rather than needing a second clause.
        where.append("tasks.due_date <= ?")
        params.append(due_before)
    if from_date:
        where.append("tasks.due_date >= ?")
        params.append(from_date)
    if to_date:
        where.append("tasks.due_date <= ?")
        params.append(to_date)

    continuation, cursor_values = cursor_clause(
        page,
        "tasks.due_date",
        "tasks.id",
        descending=False,
    )
    if continuation:
        where.append(continuation)
        params.extend(cursor_values)
    params.append(page.limit + 1)

    with db_connection() as connection:
        rows = connection.execute(
            f"""
            {TASK_ROWS_SQL}
            WHERE {" AND ".join(where)}
            ORDER BY tasks.due_date IS NULL, tasks.due_date ASC, tasks.id ASC
            LIMIT ?
            """,
            params,
        ).fetchall()

    tasks, next_cursor = split_page(rows, page.limit, lambda row: (row["due_date"], row["id"]))
    with db_connection() as connection:
        comments = comments_by_task_id(connection, [row["id"] for row in tasks])
    return Page(
        items=[task_from_row(row, comments.get(row["id"], [])) for row in tasks],
        next_cursor=next_cursor,
    )


@router.patch("/tasks/{task_id}", response_model=TaskPublic)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    user: sqlite3.Row = Depends(get_current_user),
) -> TaskPublic:
    """A partial edit of what somebody typed: author or opportunity owner
    (D-005). Not the assignee -- they may close a task, not rewrite it, which is
    the line **D-142** draws.

    `model_fields_set` decides what is written, so `null` clears a field and an
    absent key leaves it alone. An empty `PATCH` writes nothing and publishes
    nothing, the rule 3.4 applies to every write.
    """
    with db_connection() as connection:
        task = fetch_task(connection, task_id)
        opportunity_id = int(task["opportunity_id"])
        require_edit_permission(
            connection,
            opportunity_id,
            int(user["id"]),
            task["created_by"],
            "Only the task's author or the opportunity owner can edit it",
        )

        sent = payload.model_fields_set
        assignments: list[str] = []
        params: list[object] = []
        added_assignees: list[int] = []
        changing_assignees = "assignee_emails" in sent and payload.assignee_emails is not None

        if "title" in sent and payload.title is not None:
            assignments.append("title = ?")
            params.append(payload.title)
        if "description" in sent and payload.description is not None:
            assignments.append("description = ?")
            params.append(payload.description)
        if "due_date" in sent:
            assignments.append("due_date = ?")
            params.append(payload.due_date)
        if changing_assignees:
            # Resolved before anything is written, so a list naming one address
            # nobody uses writes nothing at all.
            wanted = resolve_assignees(connection, payload.assignee_emails or [])
            # Only the people who were not on it already are told, and never
            # the person doing the assigning: re-saving a task with the same
            # people is not news, and somebody who was already on it has been
            # told once.
            added_assignees = [
                user_id
                for user_id in wanted
                if user_id not in assignee_ids_of(task) and user_id != int(user["id"])
            ]

        if not assignments and not changing_assignees:
            return task_from_row(task)

        now = utc_now()
        if assignments:
            assignments.append("updated_at = ?")
            params.append(now)
            params.append(task_id)
            connection.execute(
                f"UPDATE tasks SET {', '.join(assignments)} WHERE id = ?",
                params,
            )
        if changing_assignees:
            set_assignees(connection, task_id, wanted)
            # The assignees live in another table, so the parent's own
            # `updated_at` has to be moved on purpose -- otherwise handing a
            # task to somebody else would leave the row looking untouched.
            connection.execute(
                "UPDATE tasks SET updated_at = ? WHERE id = ?",
                (now, task_id),
            )

        row = fetch_task(connection, task_id)
        # After the write, from the row read back, stamped with this write's own
        # time -- the rule every other versioned edit follows (milestone 2.10).
        record_version(connection, TASK_VERSIONS, task_id, row, int(user["id"]), now)
        notify_assigned(
            connection,
            opportunity_id=opportunity_id,
            actor_id=int(user["id"]),
            task_id=task_id,
            title=row["title"],
            due_date=row["due_date"],
            user_ids=added_assignees,
        )
        connection.commit()

    publish_opportunity_changed(opportunity_id)
    return task_from_row(row)


@router.post("/tasks/{task_id}/complete", response_model=TaskPublic)
def complete_task(
    task_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> TaskPublic:
    """Tick it off. The assignee may, as well as the author and the owner
    (**D-142**).

    Idempotent through `COALESCE`, so the first person to complete it is the one
    recorded and a second click changes nothing -- the shape resolving a thread
    already uses (3.3).
    """
    with db_connection() as connection:
        task = fetch_task(connection, task_id)
        opportunity_id = int(task["opportunity_id"])
        require_task_completion(connection, task, int(user["id"]))

        now = utc_now()
        connection.execute(
            """
            UPDATE tasks
            SET completed_at = COALESCE(completed_at, ?),
                completed_by = COALESCE(completed_by, ?),
                updated_at = ?
            WHERE id = ?
            """,
            (now, int(user["id"]), now, task_id),
        )
        row = fetch_task(connection, task_id)
        connection.commit()

    publish_opportunity_changed(opportunity_id)
    return task_from_row(row)


@router.post("/tasks/{task_id}/reopen", response_model=TaskPublic)
def reopen_task(
    task_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> TaskPublic:
    """Put it back on the list. Same rule as completing, and idempotent in the
    same way: reopening an open task is a no-op rather than an error, so a
    client that lost track of the state cannot get stuck."""
    with db_connection() as connection:
        task = fetch_task(connection, task_id)
        opportunity_id = int(task["opportunity_id"])
        require_task_completion(connection, task, int(user["id"]))

        connection.execute(
            """
            UPDATE tasks
            SET completed_at = NULL, completed_by = NULL, updated_at = ?
            WHERE id = ?
            """,
            (utc_now(), task_id),
        )
        row = fetch_task(connection, task_id)
        connection.commit()

    publish_opportunity_changed(opportunity_id)
    return task_from_row(row)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> None:
    """Author or opportunity owner, like every other delete (D-005), and a soft
    delete with an audit row so the log stays the sequence of what happened
    (invariant 7)."""
    with db_connection() as connection:
        task = fetch_task(connection, task_id)
        opportunity_id = int(task["opportunity_id"])
        require_delete_permission(
            connection,
            opportunity_id,
            int(user["id"]),
            task["created_by"],
            "Only the task's author or the opportunity owner can delete it",
        )

        soft_delete_task(connection, task_id)
        create_audit_log_entry(
            connection,
            opportunity_id=opportunity_id,
            actor_id=int(user["id"]),
            action="task_deleted",
            detail={
                "task_id": task_id,
                "title": task["title"],
                "assignee_id": task["assignee_id"],
                "author_id": task["created_by"],
            },
        )
        connection.commit()

    publish_opportunity_changed(opportunity_id)


@router.post("/tasks/{task_id}/restore", status_code=status.HTTP_204_NO_CONTENT)
def restore_deleted_task(
    task_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> None:
    """Undo the delete (milestone 2.4b's shape).

    Reads the deleted row directly rather than through `fetch_task`, which only
    answers with live ones, and refuses a task whose opportunity is deleted --
    a child cannot come back while its parent is gone, the rule every other
    restore follows. Restoring something that is not deleted is a 404, the same
    answer as one that never existed.
    """
    with db_connection() as connection:
        task = connection.execute(
            """
            SELECT tasks.*
            FROM tasks
            JOIN opportunities ON opportunities.id = tasks.opportunity_id
            WHERE tasks.id = ?
                AND tasks.deleted_at IS NOT NULL
                AND opportunities.deleted_at IS NULL
            """,
            (task_id,),
        ).fetchone()
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

        opportunity_id = int(task["opportunity_id"])
        require_delete_permission(
            connection,
            opportunity_id,
            int(user["id"]),
            task["created_by"],
            "Only the task's author or the opportunity owner can restore it",
        )

        restore_task(connection, task_id, task["deleted_at"])
        create_audit_log_entry(
            connection,
            opportunity_id=opportunity_id,
            actor_id=int(user["id"]),
            action="task_restored",
            detail={
                "task_id": task_id,
                "title": task["title"],
                "assignee_id": task["assignee_id"],
                "author_id": task["created_by"],
            },
        )
        connection.commit()

    publish_opportunity_changed(opportunity_id)


# --- A task's discussion (milestone 4.5, D-162) -----------------------------
#
# Flat and chronological: no reply, no resolve, no reaction. A task comment is
# immutable like every other comment in this app (`AGENTS.md` invariant 2), so
# there is no PATCH here either -- what exists is write it, read it with the
# task, remove it, put it back.


def fetch_task_comment(
    connection: sqlite3.Connection,
    comment_id: int,
    *,
    deleted: bool = False,
) -> sqlite3.Row:
    """One comment with the deal it hangs off, or 404.

    `deleted=True` is the restore path's mirror image: the row must be deleted
    and everything above it must not be, so a comment cannot come back under a
    task that is gone.
    """
    row: sqlite3.Row | None = connection.execute(
        f"""
        SELECT task_comments.*, users.name AS author_name, tasks.opportunity_id
        FROM task_comments
        JOIN users ON users.id = task_comments.created_by
        JOIN tasks ON tasks.id = task_comments.task_id
        JOIN opportunities ON opportunities.id = tasks.opportunity_id
        WHERE task_comments.id = ?
            AND task_comments.deleted_at IS {"NOT NULL" if deleted else "NULL"}
            AND tasks.deleted_at IS NULL
            AND opportunities.deleted_at IS NULL
        """,
        (comment_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    return row


@router.post(
    "/tasks/{task_id}/comments",
    response_model=TaskCommentPublic,
    status_code=status.HTTP_201_CREATED,
)
def create_task_comment(
    task_id: int,
    payload: TaskCommentCreate,
    user: sqlite3.Row = Depends(get_current_user),
) -> TaskCommentPublic:
    """Say something about a task. Editors may, viewers may not -- the gate
    adding a note or a comment already has, because this is adding something
    rather than changing somebody else's.

    Told to the two people a task is about: whoever wrote it and whoever owes
    it. That is `notify_note_comment`'s rule read against a task -- a set, so
    one person who is both gets one notification rather than two -- and the
    commenter is never told about their own comment.
    """
    with db_connection() as connection:
        task = fetch_task(connection, task_id)
        opportunity_id = int(task["opportunity_id"])
        require_timeline_write(connection, opportunity_id, int(user["id"]))

        cursor = connection.execute(
            """
            INSERT INTO task_comments (task_id, body, created_by, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (task_id, payload.body, int(user["id"]), utc_now()),
        )
        comment_id = int(cursor.lastrowid or 0)

        # Everyone the task is about: whoever wrote it and **everyone** it is
        # assigned to (milestone 4.6 made that a set). Read from
        # `assignee_ids_of`, not from `tasks.assignee_id` -- that column stopped
        # being written in 4.6, and reading it here is how this notification
        # silently stopped reaching assignees until `e2e/24-tasks.spec.ts`
        # noticed. A set, so somebody who is both author and assignee is told
        # once, and never the person who wrote the comment.
        recipients = {
            int(value)
            for value in (task["created_by"], *assignee_ids_of(task))
            if value is not None and int(value) != int(user["id"])
        }
        for recipient in sorted(recipients):
            create_notification(
                connection,
                recipient,
                "task_comment",
                {
                    "opportunity_id": opportunity_id,
                    "actor_id": int(user["id"]),
                    "task_id": task_id,
                    "title": task["title"],
                },
            )

        row = connection.execute(
            f"{TASK_COMMENT_ROWS_SQL} WHERE task_comments.id = ?",
            (comment_id,),
        ).fetchone()
        connection.commit()

    publish_opportunity_changed(opportunity_id)
    return task_comment_from_row(row)


@router.delete("/task-comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task_comment(
    comment_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> None:
    """Author or opportunity owner (D-005), soft and audited like every other
    delete -- and like a note's comment, which cannot be edited either, so
    removing it is the only change it can undergo."""
    with db_connection() as connection:
        comment = fetch_task_comment(connection, comment_id)
        opportunity_id = int(comment["opportunity_id"])
        require_delete_permission(
            connection,
            opportunity_id,
            int(user["id"]),
            comment["created_by"],
            "Only the comment's author or the opportunity owner can delete it",
        )

        soft_delete_task_comment(connection, comment_id)
        create_audit_log_entry(
            connection,
            opportunity_id=opportunity_id,
            actor_id=int(user["id"]),
            action="task_comment_deleted",
            detail={
                "comment_id": comment_id,
                "task_id": int(comment["task_id"]),
                "author_id": comment["created_by"],
            },
        )
        connection.commit()

    publish_opportunity_changed(opportunity_id)


@router.post("/task-comments/{comment_id}/restore", status_code=status.HTTP_204_NO_CONTENT)
def restore_deleted_task_comment(
    comment_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> None:
    """Undo the delete (2.4b's shape), scoped by the delete's own stamp: a
    comment that went with its whole task comes back with the task, and one
    deleted on its own comes back here."""
    with db_connection() as connection:
        comment = fetch_task_comment(connection, comment_id, deleted=True)
        opportunity_id = int(comment["opportunity_id"])
        require_delete_permission(
            connection,
            opportunity_id,
            int(user["id"]),
            comment["created_by"],
            "Only the comment's author or the opportunity owner can restore it",
        )

        restore_task_comment(connection, comment_id, comment["deleted_at"])
        create_audit_log_entry(
            connection,
            opportunity_id=opportunity_id,
            actor_id=int(user["id"]),
            action="task_comment_restored",
            detail={
                "comment_id": comment_id,
                "task_id": int(comment["task_id"]),
                "author_id": comment["created_by"],
            },
        )
        connection.commit()

    publish_opportunity_changed(opportunity_id)


@router.get("/tasks/{task_id}/versions", response_model=Page[TaskVersionPublic])
def list_task_versions_page(
    task_id: int,
    page: PageRequest = Depends(page_params),
    user: sqlite3.Row = Depends(get_current_user),
) -> Page[TaskVersionPublic]:
    """A task's edit history, oldest first, owner-only (milestone 4.2a).

    The fourth history to answer this question, under the same rule as the other
    three (**D-096**): `AGENTS.md` invariant 8 says the *opportunity owner* can
    read it, and this app has no admin role. Milestone 4.1 shipped an editable
    task with no history at all, which is the invariant violation the human found
    at the Phase 4 checkpoint.

    The names are resolved here rather than stored, so a history row reads
    "Gavin" rather than "3" while the snapshot keeps the ids it was written
    with -- and since milestone 4.6 that is a *set*: `assignee_ids` holds
    "3,7" and this joins each id to its name, in the ascending order the
    snapshot was written in. A version recorded before that revision carries
    one id and reads as a one-person list, because that is what it always
    meant (D-097).
    """
    continuation, cursor_values = cursor_clause(
        page,
        "task_versions.version_number",
        "task_versions.id",
        descending=False,
    )
    params: list[object] = [task_id, *cursor_values, page.limit + 1]

    with db_connection() as connection:
        task = fetch_task(connection, task_id)
        require_opportunity_owner(connection, int(task["opportunity_id"]), int(user["id"]))
        rows = connection.execute(
            f"""
            SELECT
                task_versions.*,
                editors.name AS editor_name,
                (
                    SELECT group_concat(users.name, char(31))
                    FROM users
                    WHERE instr(
                        ',' || task_versions.assignee_ids || ',',
                        ',' || users.id || ','
                    ) > 0
                ) AS assignee_names
            FROM task_versions
            JOIN users AS editors ON editors.id = task_versions.edited_by
            WHERE task_versions.task_id = ?
            {f"AND {continuation}" if continuation else ""}
            ORDER BY task_versions.version_number ASC, task_versions.id ASC
            LIMIT ?
            """,
            params,
        ).fetchall()

    rows, next_cursor = split_page(rows, page.limit, lambda row: (row["version_number"], row["id"]))
    return Page(
        items=[
            TaskVersionPublic(
                id=row["id"],
                task_id=row["task_id"],
                version_number=row["version_number"],
                title=row["title"],
                description=row["description"],
                assignees=version_assignees(row),
                due_date=row["due_date"],
                edited_by=row["edited_by"],
                editor_name=row["editor_name"],
                created_at=row["created_at"],
            )
            for row in rows
        ],
        next_cursor=next_cursor,
    )


@router.post("/tasks/{task_id}/versions/{version_number}/restore", response_model=TaskPublic)
def restore_task_version(
    task_id: int,
    version_number: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> TaskPublic:
    """Put a recorded version of a task back as the current one (milestone 4.2a).

    The fourth thing in this app whose edits can be undone, under the rules the
    other three already follow (**D-116**, **D-120**): owner-only like the
    history read beside it, the restore is itself recorded as a version so it can
    be undone in turn, and restoring what is already current writes nothing --
    which also makes a retry idempotent.

    **The assignees are restored with everything else, and notify nobody.** The
    same reasoning a restored note sends no second mention (D-120): whoever this
    task was assigned to was told when it happened, and a restore announcing it
    again would make every undo a fresh ping. A task handed to somebody *new* by
    a restore is the one case that arguably deserves one; it is not sent, because
    "you were assigned" for a task that has existed for a week is more confusing
    than silence, and the change is on the deal's activity log either way.
    """
    changed = False
    with db_connection() as connection:
        task = fetch_task(connection, task_id)
        opportunity_id = int(task["opportunity_id"])
        require_opportunity_owner(connection, opportunity_id, int(user["id"]))

        version = fetch_version(connection, TASK_VERSIONS, task_id, version_number)
        if version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task version not found",
            )
        # The task as `fetch_task` reads it, not `SELECT *`: one of the
        # snapshot's fields (`assignee_ids`, milestone 4.6) is computed from
        # `task_assignees` rather than stored on the row, so a raw read has
        # nothing to compare against.
        if not version_is_current(TASK_VERSIONS, version, task):
            changed = True
            now = utc_now()
            apply_version(connection, TASK_VERSIONS, task_id, version, {"updated_at": now})
            # And the set is put back here, because `apply_version` writes
            # columns and this one is a table. The snapshot's canonical string
            # is parsed with the same rule that wrote it.
            raw = version["assignee_ids"]
            set_assignees(
                connection,
                task_id,
                [int(value) for value in raw.split(",")] if raw else [],
            )
            row = fetch_task(connection, task_id)
            record_version(connection, TASK_VERSIONS, task_id, row, int(user["id"]), now)
            connection.commit()

        row = fetch_task(connection, task_id)

    if changed:
        publish_opportunity_changed(opportunity_id)
    return task_from_row(row)
