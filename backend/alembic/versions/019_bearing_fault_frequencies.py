"""bearing fault frequency catalogue

A reference table of defect frequency multipliers for catalogued rolling-element
bearings — FTF, BSF, BPFO and BPFI as orders of running speed, per part number.

Reference data, not plant data: no foreign keys, nothing cascades into it, and
it is the same for every tenant. The rows are loaded by
`scripts/import_bearing_frequencies.py` rather than by this migration, because
the source is an 88k-row spreadsheet that has no business living inside a
revision file.

(manufacturer, designation) is deliberately NOT unique. The catalogue lists
thousands of designations twice, and some of those pairs are genuinely
different bearings with the same part number. `source_bearing_id` carries the
catalogue's own row id and is the unique key the importer works against.

Purely additive: one new table, nothing altered, nothing dropped.

Revision ID: 019
Revises: 018
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "bearing_fault_frequencies"


def _tables() -> set[str]:
    bind = op.get_bind()
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    if TABLE in _tables():
        return

    op.create_table(
        TABLE,
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # The catalogue's own row id — traceable back to the source sheet.
        sa.Column("source_bearing_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("manufacturer", sa.String(16), nullable=False),
        sa.Column("designation", sa.String(120), nullable=False),
        # Uppercased, punctuation stripped, so a part number types loosely.
        sa.Column("search_key", sa.String(160), nullable=False),
        sa.Column("rolling_elements", sa.Integer(), nullable=False),
        # Orders of running speed, not hertz.
        sa.Column("ftf", sa.Numeric(10, 4), nullable=False),
        sa.Column("bsf", sa.Numeric(10, 4), nullable=False),
        sa.Column("bpfo", sa.Numeric(10, 4), nullable=False),
        sa.Column("bpfi", sa.Numeric(10, 4), nullable=False),
        # BPFO + BPFI == rolling_elements for a stationary outer race. Rows that
        # break the identity are loaded but flagged.
        sa.Column(
            "is_consistent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_index(f"ix_{TABLE}_source_bearing_id", TABLE, ["source_bearing_id"], unique=True)
    op.create_index(f"ix_{TABLE}_manufacturer", TABLE, ["manufacturer"])
    op.create_index(f"ix_{TABLE}_designation", TABLE, ["designation"])
    op.create_index(f"ix_{TABLE}_search_key", TABLE, ["search_key"])
    op.create_index("ix_bearing_freq_maker_designation", TABLE, ["manufacturer", "designation"])


def downgrade() -> None:
    if TABLE not in _tables():
        return
    op.drop_table(TABLE)
