"""threshold rules become channel-scoped and audited

Revision ID: 015
Revises: 014
Create Date: 2026-08-21 11:20:00.000000

feature_threshold_rules was seeded with one row per feature code, applying
everywhere. The Settings screen has always presented thresholds per channel,
because that is how they are actually used: CH-1 on a motor drive end and CH-6
on a gearbox casing do not share an RMS limit.

`channel` is nullable and NULL keeps the old meaning — the rule applies to
every channel that has no row of its own. Evaluation resolves the specific row
first and falls back to the global one, so the seeded rules keep working
untouched and a site only overrides the channels it cares about.

`updated_at` exists so the editor can show when a limit was last changed;
`updated_by` records who changed it. Both are nullable: seeded rows were never
edited by anyone.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = [c["name"] for c in sa.inspect(bind).get_columns(table)]
    return column in cols


def _index_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    return name in {ix["name"] for ix in sa.inspect(bind).get_indexes(table)}


def upgrade() -> None:
    if not _column_exists("feature_threshold_rules", "channel"):
        op.add_column(
            "feature_threshold_rules",
            sa.Column("channel", sa.Integer(), nullable=True),
        )

    if not _column_exists("feature_threshold_rules", "updated_at"):
        op.add_column(
            "feature_threshold_rules",
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )

    if not _column_exists("feature_threshold_rules", "updated_by"):
        op.add_column(
            "feature_threshold_rules",
            sa.Column(
                "updated_by",
                UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )

    # One rule per (code, machine type, channel). Postgres treats NULLs as
    # distinct in a unique index, so the global rows are excluded from this and
    # covered by the partial index below instead.
    if not _index_exists("feature_threshold_rules", "uq_threshold_rule_scope"):
        op.create_index(
            "uq_threshold_rule_scope",
            "feature_threshold_rules",
            ["feature_code", "machine_type", "channel"],
            unique=True,
            postgresql_where=sa.text("machine_type IS NOT NULL AND channel IS NOT NULL"),
        )

    if not _index_exists("feature_threshold_rules", "uq_threshold_rule_global"):
        op.create_index(
            "uq_threshold_rule_global",
            "feature_threshold_rules",
            ["feature_code"],
            unique=True,
            postgresql_where=sa.text("machine_type IS NULL AND channel IS NULL"),
        )

    if not _index_exists("feature_threshold_rules", "uq_threshold_rule_channel"):
        op.create_index(
            "uq_threshold_rule_channel",
            "feature_threshold_rules",
            ["feature_code", "channel"],
            unique=True,
            postgresql_where=sa.text("machine_type IS NULL AND channel IS NOT NULL"),
        )


def downgrade() -> None:
    for name in (
        "uq_threshold_rule_channel",
        "uq_threshold_rule_global",
        "uq_threshold_rule_scope",
    ):
        if _index_exists("feature_threshold_rules", name):
            op.drop_index(name, table_name="feature_threshold_rules")

    for column in ("updated_by", "updated_at", "channel"):
        if _column_exists("feature_threshold_rules", column):
            op.drop_column("feature_threshold_rules", column)
