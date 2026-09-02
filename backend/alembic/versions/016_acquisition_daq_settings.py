"""acquisition/DAQ settings become per-sensor instead of module constants

Window, averaging and overlap were fixed constants in
`services/acquisition_config.py`, so every device received the same acquisition
JSON. They are now stored per sensor alongside the rate/LOR/fmax that were
already configurable.

Purely additive: three nullable columns with server defaults equal to the
constants they replace, so every existing row keeps behaving exactly as before
and nothing is rewritten or dropped.

Revision ID: 016
Revises: 015
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "plot_configurations"

# Values previously hard-coded in acquisition_config.py.
DEFAULT_WINDOW = "HANNING"
DEFAULT_AVERAGING = 1
DEFAULT_OVERLAP = 0


def _columns() -> set[str]:
    bind = op.get_bind()
    return {c["name"] for c in sa.inspect(bind).get_columns(TABLE)}


def upgrade() -> None:
    existing = _columns()

    if "window_type" not in existing:
        op.add_column(
            TABLE,
            sa.Column(
                "window_type",
                sa.String(20),
                nullable=False,
                server_default=DEFAULT_WINDOW,
            ),
        )
    if "averaging" not in existing:
        op.add_column(
            TABLE,
            sa.Column(
                "averaging",
                sa.Integer(),
                nullable=False,
                server_default=str(DEFAULT_AVERAGING),
            ),
        )
    if "overlap_percent" not in existing:
        op.add_column(
            TABLE,
            sa.Column(
                "overlap_percent",
                sa.Integer(),
                nullable=False,
                server_default=str(DEFAULT_OVERLAP),
            ),
        )


def downgrade() -> None:
    existing = _columns()
    for name in ("overlap_percent", "averaging", "window_type"):
        if name in existing:
            op.drop_column(TABLE, name)
