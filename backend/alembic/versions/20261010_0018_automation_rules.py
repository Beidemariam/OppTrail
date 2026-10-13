"""Automations: a rule table and the log of what each rule did

Milestone 6.3, `docs/FEATURES.md` §11: *"if nothing has happened in two weeks,
remind me" is a rule every rep keeps in their head and forgets under pressure.*

§11 is emphatic that this is a **constrained, legible rule builder and not a
workflow engine**, and the schema is where most of that constraint lives:

- **One trigger, one ANDed condition list, one action.** Not a graph, not a
  step list -- three columns, so a rule that branches cannot be stored. The
  trigger and action parameters are JSON (`trigger_config`, `action_config`)
  because each kind takes different keys, and `conditions` is a JSON array of
  `{field, op, value}` triples. `json_valid` is the constraint that makes
  those columns mean what they say, the same choice revision 0016 made for
  `custom_values`; what is *in* them is validated by `app/automations.py` on
  write, which is ADR 0006's "validate on write, never trust on read" applied
  to a second JSON column.
- **`enabled` and `archived_at`, and no DELETE.** The pair is deliberate and
  they are not the same switch: `enabled` is the toggle somebody flips while
  working out whether a rule does what they meant, and `archived_at` retires
  it for good. Neither removes the row, because `automation_runs.rule_id`
  points at it -- a log that says "rule 4 changed this deal's stage" is
  worthless if rule 4 can vanish. Same shape as `custom_field_definitions`
  (milestone 6.1), and the reason this table is not in
  `soft_delete.USER_DATA_TABLES` either: configuration that retires rather
  than content that deletes.
- **`automation_runs` is the traceability half of §11's own requirement**
  ("every automated write produces a traceable system entry naming the
  rule"). The system entry is the user-visible half and `entry_id` points at
  it; this table is what answers "why did that happen" for a rule that
  matched and *declined* to act -- the creator lacked the role, the action
  was a no-op, the deal moved underneath it.
- **A dry run is a row too** (`dry_run = 1`), with the same outcome it would
  have had. That is what makes §11's "always dry-runnable" inspectable rather
  than a response body somebody has to screenshot: the preview and the real
  run are read back through one list, and `entry_id` is NULL on every dry row
  because nothing was written.

`failed` is one of the three outcomes and nothing writes it yet. That is
deliberate and has a precedent in this schema: `notifications.grouped_key`
has ridden along unpopulated since revision 0003 because its caller is a
later milestone (**D-095**). A firing that raises today rolls back whole;
milestone 6.5's scheduler is what needs the outcome recorded rather than
raised, since a tick has nobody to answer a 500 to.

`outcome` is three values and `dry_run` is a flag, rather than a fourth
`previewed` outcome: "what would have happened" and "what happened" are the
same question asked in two modes, and collapsing them would mean a reader
could no longer ask "would this have applied?" of a preview.

No index on `automation_runs(opportunity_id)`. The log is read per rule (the
builder's "what did this do") and the volume is bounded by matches rather than
by deals -- a per-opportunity view of automation history is what the activity
log would be for, and nothing asks for it yet.

Revision ID: 0018_automation_rules
Revises: 0017_activity_indexes
Create Date: 2026-10-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018_automation_rules"
down_revision: str | None = "0017_activity_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE automation_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            trigger_type TEXT NOT NULL CHECK (trigger_type IN (
                'stage_changed',
                'entry_created',
                'field_changed',
                'no_activity',
                'close_date_approaching'
            )),
            trigger_config TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(trigger_config)),
            conditions TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(conditions)),
            action_type TEXT NOT NULL CHECK (action_type IN (
                'create_task',
                'notify_user',
                'add_entry',
                'change_stage'
            )),
            action_config TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(action_config)),
            enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
            created_by INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            archived_at TEXT
        )
        """
    )
    # The hot read: a human write asks "which live rules watch this trigger",
    # once per stage change, field edit and entry. Partial, so the index holds
    # only the rules that can actually fire.
    op.execute(
        """
        CREATE INDEX idx_automation_rules_armed
        ON automation_rules (trigger_type, id)
        WHERE archived_at IS NULL AND enabled = 1
        """
    )
    # The builder's own read, and what the per-creator cap counts.
    op.execute(
        """
        CREATE INDEX idx_automation_rules_creator
        ON automation_rules (created_by, id)
        WHERE archived_at IS NULL
        """
    )

    op.execute(
        """
        CREATE TABLE automation_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id INTEGER NOT NULL REFERENCES automation_rules(id),
            opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
            outcome TEXT NOT NULL CHECK (outcome IN ('applied', 'skipped', 'failed')),
            reason TEXT,
            entry_id INTEGER REFERENCES timeline_entries(id),
            dry_run INTEGER NOT NULL DEFAULT 0 CHECK (dry_run IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        )
        """
    )
    # Newest-last per rule, which is both the log's reading order and the
    # keyset it pages by. Ends in the id, like every paginated ORDER BY here.
    op.execute(
        """
        CREATE INDEX idx_automation_runs_rule
        ON automation_runs (rule_id, id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_automation_runs_rule")
    op.execute("DROP TABLE IF EXISTS automation_runs")
    op.execute("DROP INDEX IF EXISTS idx_automation_rules_creator")
    op.execute("DROP INDEX IF EXISTS idx_automation_rules_armed")
    op.execute("DROP TABLE IF EXISTS automation_rules")
