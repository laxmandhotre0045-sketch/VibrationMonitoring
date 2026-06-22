"""upload history fields — original_filename, source, date-range index

Revision ID: 009
Revises: 008
Create Date: 2026-06-22 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sensor_data_uploads",
        sa.Column("original_filename", sa.String(255), nullable=True),
    )
    op.add_column(
        "sensor_data_uploads",
        sa.Column(
            "source",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'manual'"),
        ),
    )

    op.execute(
        """
        UPDATE sensor_data_uploads AS u
        SET original_filename = d.original_filename
        FROM measurement_upload_data AS d
        WHERE d.upload_id = u.id
          AND u.original_filename IS NULL
        """
    )

    op.create_index(
        "ix_sensor_data_uploads_sensor_id_created_at",
        "sensor_data_uploads",
        ["sensor_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_sensor_data_uploads_sensor_id_created_at",
        table_name="sensor_data_uploads",
    )
    op.drop_column("sensor_data_uploads", "source")
    op.drop_column("sensor_data_uploads", "original_filename")
