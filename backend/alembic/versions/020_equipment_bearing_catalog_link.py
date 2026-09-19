"""link equipment bearings to the bearing catalogue

Two nullable columns on `equipment_masters` holding the catalogue's Bearing ID for the
drive-end and non-drive-end bearing, so the Equipment Master can resolve a
machine's bearings to their FTF/BSF/BPFO/BPFI without an engineer copying four
numbers off a datasheet.

Only the id is stored. Copying the catalogue's seven fields onto every machine
would duplicate reference data and go stale the moment the catalogue is
corrected, and `bearing_fault_frequencies.source_bearing_id` is indexed, so the
join is cheap.

No foreign key on purpose: the catalogue is optional reference data that a
deployment may never load, and an equipment record has to stay saveable when
the table is empty. `bearing_number_de` / `_nde` remain the free-text fields
they always were — a machine whose bearing is not in the catalogue still
records what is fitted.

Purely additive: two nullable columns, nothing altered, nothing dropped.

Revision ID: 020
Revises: 019
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "equipment_masters"
COLUMNS = ("bearing_de_catalog_id", "bearing_nde_catalog_id")


def _existing_columns() -> set[str]:
    bind = op.get_bind()
    return {col["name"] for col in sa.inspect(bind).get_columns(TABLE)}


def upgrade() -> None:
    existing = _existing_columns()
    for column in COLUMNS:
        if column not in existing:
            op.add_column(TABLE, sa.Column(column, sa.Integer(), nullable=True))


def downgrade() -> None:
    existing = _existing_columns()
    for column in COLUMNS:
        if column in existing:
            op.drop_column(TABLE, column)
