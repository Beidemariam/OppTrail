"""An index on the entry an automation run wrote

Milestone 6.3a. The deal's owner asked to be able to delete an entry a rule
wrote, in case a mistaken rule acted on their deal (**D-181**) -- and that
needs the question "did an automation write this entry" answered for a whole
page of a timeline, not for one row.

Revision 0018 said there was no index here because "the log is read per rule
and the volume is bounded by matches rather than by deals". That was true of
the only reader it had. This is the second reader, and it comes at the
timeline from the other direction: `automation_rule_ids_by_entry_id` asks
`WHERE entry_id IN (...)` once per page, which without this index is a scan of
every run row per page of fifty cards.

Partial, because a run that wrote nothing -- a skip, or any dry run -- has no
entry to be asked about, and those are the majority of rows in a busy log.

Revision ID: 0019_automation_run_entry_index
Revises: 0018_automation_rules
Create Date: 2026-10-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0019_automation_run_entry_index"
down_revision: str | None = "0018_automation_rules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX idx_automation_runs_entry
        ON automation_runs (entry_id, rule_id)
        WHERE entry_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_automation_runs_entry")
