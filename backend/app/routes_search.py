import sqlite3

from fastapi import APIRouter, Depends, Query

from .auth import get_current_user
from .database import db_connection
from .pagination import Page, PageRequest, page_params
from .schemas import SearchResultPublic
from .search import search

# Search is cross-opportunity, so it exists only on the paginated surface: a
# ranked result set with no limit and no cursor is the shape the v2 envelope
# was introduced to stop shipping (`docs/ARCHITECTURE.md`, "Pagination").
router = APIRouter(prefix="/api/v2", tags=["search"])


@router.get("/search", response_model=Page[SearchResultPublic])
def search_everything(
    q: str,
    page: PageRequest = Depends(page_params),
    type: str | None = None,
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
    author_id: int | None = None,
    user: sqlite3.Row = Depends(get_current_user),
) -> Page[SearchResultPublic]:
    """Ranked, snippeted matches in entries, notes, comments and attachment
    filenames (the fourth kind since milestone 4.8), across every
    opportunity this user can read and no others (`FEATURES.md` §13).

    The filters are the timeline's, by the same names: `type` is the type of
    the entry a match sits under, `author_id` is who wrote the matched item,
    and the date window is over the item's own timestamp.
    """
    with db_connection() as connection:
        items, next_cursor = search(
            connection,
            int(user["id"]),
            q,
            page,
            entry_type=type,
            author_id=author_id,
            from_date=from_date,
            to_date=to_date,
        )

    return Page(items=items, next_cursor=next_cursor)
