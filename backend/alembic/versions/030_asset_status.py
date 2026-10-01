"""The expert's judgement of an asset's health

Status answers a different question from every grade already in this schema.
`measurement_channel_features.status` is what the thresholds computed about one
number; this is what a person concluded about a machine after looking. The two
disagree often, and they are supposed to: an analyst who has seen the spectrum
and knows the pump is being replaced on Friday sets Critical and stops the
screen arguing with them.

One row per asset, replaced in place. It is not a history table — what changed
and why belongs with the finding that recorded it (SNV-STA-02, migration 031),
and duplicating that here would give two answers that drift apart.

Scoped to the two levels this schema has: the machine and the sensor. The
`scope` column is a string rather than an enum so that components and measuring
points, when the hierarchy gains them, are a code change rather than a type
rewrite on a table with rows in it.

Revision ID: 030
Revises: 029
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "030"
down_revision: Union[str, None] = "029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "asset_status"


def _table_exists(name: str) -> bool:
    return name in set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if _table_exists(TABLE):
        return

    op.create_table(
        TABLE,
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("asset_id", UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="Unknown"),
        # A machine somebody judged by hand stops inheriting from its sensors.
        # Without this the next capture would quietly undo the judgement.
        sa.Column("overridden", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "set_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "set_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # One current status per asset: a second row for the same asset would be
    # two answers to a question that has one.
    op.create_unique_constraint(
        "uq_asset_status_scope_asset", TABLE, ["scope", "asset_id"]
    )

    # Every screen asks "what is this machine's status", so the lookup is by
    # scope and asset, and the fleet views read every machine at once.
    op.create_index("ix_asset_status_scope", TABLE, ["scope"])

    # Only the seven documented values. A typo'd status is worse than no
    # status: it reads as a state nobody can place in the ordering.
    op.create_check_constraint(
        "ck_asset_status_value",
        TABLE,
        "status IN ('Normal','Warning','Alarm','Critical','Unknown',"
        "'Out of service','Not monitored')",
    )
    op.create_check_constraint(
        "ck_asset_status_scope",
        TABLE,
        "scope IN ('machine','sensor','component','point')",
    )


def downgrade() -> None:
    if _table_exists(TABLE):
        op.drop_table(TABLE)
