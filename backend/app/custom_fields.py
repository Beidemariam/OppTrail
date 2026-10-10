"""Custom fields: the typed metadata, and what a value has to satisfy.

ADR 0006 and `docs/FEATURES.md` §3 (milestone 6.1). Definitions live in a
table so the UI, the validation and the filter builder read one source;
values live in one JSON column per row so rendering needs no joins.

Two rules from the ADR run through everything here:

- **Validation happens on write, against the live definition set.** A value
  for a field nobody defined is a 422, as is a value of the wrong type or a
  `select` outside its options -- because the alternative is discovering it
  when a screen tries to render it.
- **The JSON column is never trusted on read.** `visible_values` drops any
  key without a live definition, so archiving a field hides it everywhere
  without rewriting a single row. That is the property that makes
  archive-and-recreate the answer to a type change (the ADR's last
  consequence) rather than a data migration per field.
"""

import json
import sqlite3
from typing import Any

from fastapi.exceptions import RequestValidationError

from .schemas import CustomFieldEntity, CustomFieldType, canonical_date

DEFINITION_ROWS_SQL = """
    SELECT id, entity_type, key, label, type, options, required, position,
           created_by, created_at, updated_at, archived_at
    FROM custom_field_definitions
"""


def definition_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "entity_type": row["entity_type"],
        "key": row["key"],
        "label": row["label"],
        "type": row["type"],
        "options": json.loads(row["options"]),
        "required": bool(row["required"]),
        "position": row["position"],
        "created_by": row["created_by"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "archived_at": row["archived_at"],
    }


def live_definitions(
    connection: sqlite3.Connection,
    entity_type: CustomFieldEntity,
) -> list[dict[str, Any]]:
    """The fields currently offered for one entity type, in display order.

    Ordered by `position` then `id`, so a definition set with no explicit
    ordering is still stable -- the same reason every paginated `ORDER BY` in
    this project ends in the row id.
    """
    rows = connection.execute(
        f"""
        {DEFINITION_ROWS_SQL}
        WHERE entity_type = ? AND archived_at IS NULL
        ORDER BY position, id
        """,
        (entity_type,),
    ).fetchall()
    return [definition_from_row(row) for row in rows]


def stored_values(raw: str | None) -> dict[str, Any]:
    """The JSON column as a dict, tolerating anything that is not one.

    The column is `NOT NULL DEFAULT '{}'` with a `json_valid` check, so this
    should never have to fall back -- but a database bridged from before the
    revision, or edited by hand, is a real state and a malformed value here
    must not 500 a dashboard the way an unparseable timestamp once did
    (`CLAUDE.md`, "Timestamps").
    """
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def visible_values(
    raw: str | None,
    definitions: list[dict[str, Any]],
) -> dict[str, Any]:
    """What a reader is shown: stored values, minus anything undefined.

    Unknown keys are dropped rather than returned, which is ADR 0006's "the
    JSON column is never trusted on read". An archived field's values stay in
    the row and stop being visible, so archiving is reversible and costs no
    migration.
    """
    values = stored_values(raw)
    return {
        definition["key"]: values[definition["key"]]
        for definition in definitions
        if definition["key"] in values
    }


class CustomFieldError(ValueError):
    """A value that does not satisfy its definition, named by field key."""

    def __init__(self, key: str, message: str) -> None:
        super().__init__(message)
        self.key = key
        self.message = message


def _validated_scalar(definition: dict[str, Any], value: Any) -> Any:
    field_type: CustomFieldType = definition["type"]
    key = definition["key"]

    if field_type == "text":
        if not isinstance(value, str):
            raise CustomFieldError(key, "must be text")
        return value.strip()

    if field_type == "number":
        # `bool` is an `int` in Python, and a checkbox arriving in a number
        # field is a mistake worth naming rather than storing as 1.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise CustomFieldError(key, "must be a number")
        return value

    if field_type == "date":
        if not isinstance(value, str):
            raise CustomFieldError(key, "must be a date (YYYY-MM-DD)")
        try:
            # One date format, validated at the boundary, exactly as every
            # other date in this project is (`time_utils.py`).
            return canonical_date(value)
        except ValueError as exc:
            raise CustomFieldError(key, str(exc)) from exc

    if field_type == "checkbox":
        if not isinstance(value, bool):
            raise CustomFieldError(key, "must be true or false")
        return value

    if field_type == "select":
        if not isinstance(value, str):
            raise CustomFieldError(key, "must be one of the field's options")
        if value not in definition["options"]:
            raise CustomFieldError(key, "must be one of the field's options")
        return value

    if field_type == "user":
        if isinstance(value, bool) or not isinstance(value, int):
            raise CustomFieldError(key, "must be a user id")
        return value

    raise CustomFieldError(key, f"unsupported field type: {field_type}")


def _validated_multi_select(definition: dict[str, Any], value: Any) -> list[str]:
    key = definition["key"]
    if not isinstance(value, list):
        raise CustomFieldError(key, "must be a list of the field's options")
    for item in value:
        if not isinstance(item, str) or item not in definition["options"]:
            raise CustomFieldError(key, "must be a list of the field's options")
    # De-duplicated and ordered as the definition orders its options, so two
    # writes of the same choices store the same JSON -- the reasoning
    # `task_versions.assignee_ids` uses for a set it has to compare as text.
    return [option for option in definition["options"] if option in value]


def validated_values(
    connection: sqlite3.Connection,
    entity_type: CustomFieldEntity,
    submitted: dict[str, Any] | None,
    existing: str | None = None,
) -> str:
    """The JSON to store, or raise `CustomFieldError`.

    `submitted` is a whole value set, not a patch: a key left out is a value
    cleared, and `None` for a key is the same thing -- there is no way to say
    "leave this one alone", because a JSON column is written whole and a
    partial merge would make an empty field indistinguishable from an absent
    one. `existing` is what the row holds, used only when `submitted` is
    `None` (the caller did not mention custom fields at all), so an ordinary
    `PATCH` of a name does not silently clear them.

    A `required` field must be present and non-empty **when the caller
    submits a value set at all**. A write that does not mention custom fields
    keeps what the row had, which is what lets a field be made required
    without invalidating every existing row -- the archive-and-recreate
    reasoning applied to a flag rather than to a type.
    """
    definitions = live_definitions(connection, entity_type)
    if submitted is None:
        return json.dumps(visible_values(existing, definitions), sort_keys=True)

    by_key = {definition["key"]: definition for definition in definitions}
    for key in submitted:
        if key not in by_key:
            raise CustomFieldError(key, "is not a field on this record")

    stored: dict[str, Any] = {}
    for definition in definitions:
        key = definition["key"]
        value = submitted.get(key)
        empty = value is None or value == "" or value == []
        if empty:
            if definition["required"]:
                raise CustomFieldError(key, "is required")
            continue
        if definition["type"] == "multi_select":
            stored[key] = _validated_multi_select(definition, value)
        else:
            stored[key] = _validated_scalar(definition, value)

    # Sorted so the column's text is a function of its content: two equal
    # value sets serialise identically, which keeps a version snapshot
    # comparable as a string (`versioning.version_is_current`).
    return json.dumps(stored, sort_keys=True)


def custom_values_or_422(
    connection: sqlite3.Connection,
    entity_type: CustomFieldEntity,
    submitted: dict[str, Any] | None,
    existing: str | None = None,
) -> str:
    """`validated_values`, with a refusal the client can act on.

    Raised as a `RequestValidationError` rather than an `HTTPException`
    because that is what this is: a request whose body does not validate.
    The difference matters to the caller -- `errors.py`'s handler turns it
    into the envelope's `fields` map, keyed `custom_values.<key>`, which is
    the half of a 422 that tells a form which input to mark (`docs/REVIEW.md`
    M4). An `HTTPException` would answer the same status with no field at
    all, which is the flat "Request failed" that envelope exists to replace.

    The validation needs the database -- a value is only wrong relative to a
    definition -- so it cannot live in the Pydantic model, which is why this
    is the one validation path in the app that runs inside a route and still
    answers like a schema failure.
    """
    try:
        return validated_values(connection, entity_type, submitted, existing)
    except CustomFieldError as exc:
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("body", "custom_values", exc.key),
                    "msg": exc.message,
                    "input": (submitted or {}).get(exc.key),
                }
            ]
        ) from exc
