"""The dashboard read (milestone 6.2, `docs/FEATURES.md` §10).

One route, six aggregations, computed live. Like search, this is a read that
**spans opportunities**, so it cannot resolve a role first the way every
per-record route does -- `app/dashboard.py` embeds
`permissions.ACCESSIBLE_OPPORTUNITY_IDS_SQL` in each query instead, and every
number that comes back is one this caller may see. Two managers asking the
same question get different answers, which is correct and is the same
property a shared saved view has (D-076).

Not paginated, unlike every other collection read: these are six fixed-size
summaries rather than a list somebody walks. The two that could grow -- the
stalled list and the activity series -- take explicit caps instead, because a
cursor over an aggregate is a cursor over something that changes under it.
"""

import sqlite3

from fastapi import APIRouter, Depends, Query

from .auth import get_current_user
from .dashboard import (
    activity_per_rep,
    average_time_in_stage,
    forecast,
    pipeline_by_stage,
    stalled_opportunities,
    summed_currency,
    win_loss,
)
from .database import db_connection
from .schemas import DashboardPublic

router = APIRouter(prefix="/api/v2/dashboard", tags=["dashboard"])

# Eight weeks of activity and fifty stalled deals. Both are what a screen can
# show rather than what the database holds: the numbers are a reading window,
# and asking for more is a parameter rather than a page.
DEFAULT_ACTIVITY_WEEKS = 8
MAX_ACTIVITY_WEEKS = 52
DEFAULT_STALLED_LIMIT = 50
MAX_STALLED_LIMIT = 200


@router.get("", response_model=DashboardPublic)
def read_dashboard(
    since: str | None = Query(
        default=None,
        description="Win/loss period floor, as a canonical UTC timestamp or a date.",
    ),
    weeks: int = Query(default=DEFAULT_ACTIVITY_WEEKS, ge=1, le=MAX_ACTIVITY_WEEKS),
    stalled_limit: int = Query(default=DEFAULT_STALLED_LIMIT, ge=1, le=MAX_STALLED_LIMIT),
    user: sqlite3.Row = Depends(get_current_user),
) -> DashboardPublic:
    user_id = int(user["id"])
    with db_connection() as connection:
        return DashboardPublic(
            currency=summed_currency(connection, user_id),
            pipeline=pipeline_by_stage(connection, user_id),
            win_loss=win_loss(connection, user_id, since),
            time_in_stage=average_time_in_stage(connection, user_id),
            stalled=stalled_opportunities(connection, user_id, stalled_limit),
            activity=activity_per_rep(connection, user_id, weeks),
            forecast=forecast(connection, user_id),
        )
