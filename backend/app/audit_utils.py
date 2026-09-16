import json
import sqlite3
from typing import cast

from .schemas import AUDIT_DETAIL_MODELS, AuditDetail
from .time_utils import utc_now


def create_audit_log_entry(
    connection: sqlite3.Connection,
    opportunity_id: int,
    actor_id: int,
    action: str,
    detail: dict[str, object],
) -> None:
    connection.execute(
        """
        INSERT INTO audit_log_entries (opportunity_id, actor_id, action, detail, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (opportunity_id, actor_id, action, json.dumps(detail, sort_keys=True), utc_now()),
    )


def parse_audit_detail(action: str, raw_detail: str) -> AuditDetail:
    model = AUDIT_DETAIL_MODELS[action]
    return cast(AuditDetail, model.model_validate_json(raw_detail))
