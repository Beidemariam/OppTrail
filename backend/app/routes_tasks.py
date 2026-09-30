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
    require_timeline_write,
)
from .schemas import TaskCreate, TaskPublic, TaskUpdate
from .soft_delete import restore_task, soft_delete_task
from .time_utils import utc_now

router = APIRouter(prefix="/api/v2", tags=["tasks"])

# Every read of a task answers with the deal it belongs to and the people on it,
# because My Tasks shows tasks from several opportunities at once and a bare
# title is not actionable. Shared for the reason `ENTRY_ROWS_SQL` is: five reads
# answer with a task and a client cannot tell which one produced the row.
TASK_ROWS_SQL = """
    SELECT
        tasks.*,
        opportunities.name AS opportunity_name,
        timeline_entries.title AS entry_title,
        assignees.name AS assignee_name,
        authors.name AS author_name,
        completers.name AS completed_by_name
    FROM tasks
    JOIN opportunities ON opportunities.id = tasks.opportunity_id
    LEFT JOIN timeline_entries
        ON timeline_entries.id = tasks.entry_id
        AND timeline_entries.deleted_at IS NULL
    LEFT JOIN users AS assignees ON assignees.id = tasks.assignee_id
    LEFT JOIN users AS authors ON authors.id = tasks.created_by
    LEFT JOIN users AS completers ON completers.id = tasks.completed_by
"""


def task_from_row(row: sqlite3.Row) -> TaskPublic:
    return TaskPublic(
        id=row["id"],
        opportunity_id=row["opportunity_id"],
        opportunity_name=row["opportunity_name"],
        entry_id=row["entry_id"],
        # `NULL` when the entry it came from has been deleted, which is
        # deliberate: an action item outlives the record of where it came from.
        entry_title=row["entry_title"],
        title=row["title"],
        assignee_id=row["assignee_id"],
        assignee_name=row["assignee_name"],
        due_date=row["due_date"],
        completed_at=row["completed_at"],
        completed_by=row["completed_by"],
        completed_by_name=row["completed_by_name"],
        created_by=row["created_by"],
        author_name=row["author_name"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
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
    """Who may tick a task off: its author, the opportunity owner, or **the
    person it is assigned to** (**D-142**).

    The first two are D-005's rule, resolved through the same
    `require_timeline_write` gate every other write uses. The third is the
    addition, and the reason this function exists at all: a task assigned to
    somebody who cannot close it is worse than no task, and the assignee is the
    one person the row itself names as responsible.
    """
    role = require_timeline_write(connection, int(task["opportunity_id"]), user_id)
    if role == "owner":
        return
    if user_id in (task["created_by"], task["assignee_id"]):
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

        assignee_id = (
            resolve_assignee(connection, payload.assignee_email) if payload.assignee_email else None
        )
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
                opportunity_id, entry_id, title, assignee_id, due_date,
                created_by, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                opportunity_id,
                payload.entry_id,
                payload.title,
                assignee_id,
                payload.due_date,
                int(user["id"]),
                now,
                now,
            ),
        )
        task_id = int(cursor.lastrowid or 0)

        if assignee_id is not None and assignee_id != int(user["id"]):
            create_notification(
                connection,
                assignee_id,
                "task_assigned",
                {
                    "opportunity_id": opportunity_id,
                    "actor_id": int(user["id"]),
                    "task_id": task_id,
                    "title": payload.title,
                    "due_date": payload.due_date,
                },
            )

        row = fetch_task(connection, task_id)
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
    return Page(items=[task_from_row(row) for row in tasks], next_cursor=next_cursor)


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
        where.append("tasks.assignee_id = ?")
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
    return Page(items=[task_from_row(row) for row in tasks], next_cursor=next_cursor)


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
        notify_assignee: int | None = None

        if "title" in sent and payload.title is not None:
            assignments.append("title = ?")
            params.append(payload.title)
        if "due_date" in sent:
            assignments.append("due_date = ?")
            params.append(payload.due_date)
        if "assignee_email" in sent:
            assignee_id = (
                resolve_assignee(connection, payload.assignee_email)
                if payload.assignee_email
                else None
            )
            assignments.append("assignee_id = ?")
            params.append(assignee_id)
            # Told only when the assignee actually changes, and never to the
            # person doing the assigning: re-saving a task with the same
            # assignee is not news.
            if assignee_id is not None and assignee_id not in (
                task["assignee_id"],
                int(user["id"]),
            ):
                notify_assignee = assignee_id

        if not assignments:
            return task_from_row(task)

        assignments.append("updated_at = ?")
        params.append(utc_now())
        params.append(task_id)
        connection.execute(
            f"UPDATE tasks SET {', '.join(assignments)} WHERE id = ?",
            params,
        )

        row = fetch_task(connection, task_id)
        if notify_assignee is not None:
            create_notification(
                connection,
                notify_assignee,
                "task_assigned",
                {
                    "opportunity_id": opportunity_id,
                    "actor_id": int(user["id"]),
                    "task_id": task_id,
                    "title": row["title"],
                    "due_date": row["due_date"],
                },
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
