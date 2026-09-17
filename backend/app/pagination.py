"""Cursor pagination for the `/api/v2` surface.

`docs/ARCHITECTURE.md` ("Pagination"): every collection endpoint is paginated
from the start, `?limit&cursor` in and `{"items": [...], "next_cursor": null}`
out. The reason is not load — it is that adding pagination to a shape clients
already consume is a breaking change, which is why it lands with the version
boundary rather than after the view layer is built (review blocker B3).

Keyset, not offset: every paginated query here already has a total order
(`ORDER BY <sort column>, <id>`), so the cursor carries the last row's sort
value and id and the next page continues strictly after it. An OFFSET would
skip or repeat rows when something is inserted or soft-deleted between two
requests, which is exactly what a timeline does while it is being read.
"""

import base64
import binascii
import json
from collections.abc import Callable, Sequence
from typing import Any

from fastapi import HTTPException, Query, status
from pydantic import BaseModel

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class Page[ItemT](BaseModel):
    """The one response shape every `/api/v2` collection endpoint returns.

    `next_cursor` is null on the last page, so a client loops until it is null
    rather than comparing counts against the limit it asked for.
    """

    items: list[ItemT]
    next_cursor: str | None = None


class PageRequest(BaseModel):
    """`?limit&cursor`, validated at the boundary like every other input.

    An out-of-range `limit` is a 422 from FastAPI's own validation rather than a
    silent clamp: a client asking for 10,000 rows has a bug, and answering 200
    of them without saying so hides it.
    """

    limit: int
    cursor: str | None


def page_params(
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    cursor: str | None = Query(default=None),
) -> PageRequest:
    return PageRequest(limit=limit, cursor=cursor)


def encode_cursor(values: Sequence[object]) -> str:
    """Opaque to clients, JSON underneath, so a sort value keeps its type.

    Padding is stripped because `=` is legal in a query string but routinely
    mangled by intermediaries that re-encode one; `decode_cursor` puts it back.
    """
    raw = json.dumps(list(values), separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str, arity: int) -> list[Any]:
    """Reject anything that is not a cursor this module produced.

    A cursor is interpolated into a WHERE clause as a bound parameter, so a bad
    one cannot do damage — but it can produce a confusing empty page, and
    `400 invalid_cursor` says what actually went wrong.
    """
    padding = "=" * (-len(cursor) % 4)
    try:
        values = json.loads(base64.urlsafe_b64decode(cursor + padding))
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise _invalid_cursor() from exc
    if not isinstance(values, list) or len(values) != arity:
        raise _invalid_cursor()
    return values


def _invalid_cursor() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid pagination cursor",
    )


def cursor_clause(
    page: PageRequest,
    sort_column: str,
    id_column: str,
    *,
    descending: bool,
) -> tuple[str | None, list[object]]:
    """The `WHERE` fragment that continues after the cursor's row, and its
    bound parameters. `(None, [])` on the first page, which asks for no
    fragment at all.

    Two columns rather than an arbitrary tuple because that is the shape every
    paginated query here has: one sort column, and the row id as the tie-break
    that makes the order total.
    """
    if page.cursor is None:
        return None, []
    sort_value, row_id = decode_cursor(page.cursor, 2)
    comparison = "<" if descending else ">"
    fragment = (
        f"({sort_column} {comparison} ? OR ({sort_column} = ? AND {id_column} {comparison} ?))"
    )
    return fragment, [sort_value, sort_value, row_id]


def split_page[RowT](
    rows: Sequence[RowT],
    limit: int,
    cursor_values: Callable[[RowT], Sequence[object]],
) -> tuple[list[RowT], str | None]:
    """Trim the `limit + 1` rows the query asked for down to a page.

    Fetching one extra row is how "is there a next page" is answered without a
    second `COUNT(*)` over the same predicate — and it means the last page
    reports `next_cursor: null` instead of handing back a cursor that resolves
    to nothing.
    """
    if len(rows) <= limit:
        return list(rows), None
    page = list(rows[:limit])
    return page, encode_cursor(cursor_values(page[-1]))
