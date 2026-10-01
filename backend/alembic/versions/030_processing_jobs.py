"""processing_jobs: the queue the worker polls

One row per upload describing deferred work — plots, features and the alert
count — that used to run inside POST /api/v1/measurements/upload. The request
now parses and stores, then queues; a separate worker process picks the row up
and runs the rest of the pipeline.

No broker table pair, no Redis: `SELECT … FOR UPDATE SKIP LOCKED` on this table
is a work queue, and the database is already shared by every process.

`upload_id` is unique on purpose. Enqueueing upserts, so re-uploading or
reprocessing the same upload re-arms one row instead of piling up duplicates
for the same work; `attempts` carries what separate rows would have recorded.

The partial index on (status, available_at) is what the claim query reads, and
it only covers rows still in play — a finished job is never a candidate, so
keeping succeeded and failed rows out of the index keeps it small however long
the table is retained.

Purely additive: one new table, nothing altered, nothing dropped.

**Why this is 030 and not 021.** It was written as 021, inserted ahead of
the migration that already held that number, which was renamed to 021a to
make room. That works on a database built from scratch and silently does
nothing on every database that already exists.

Alembic records only where a database is now, not the path it took. A
database already at 028 is never walked backwards to pick up a revision
inserted behind it: `upgrade head` computes 028 -> 029 and stops. The table
is never created, alembic still reports head, and the first thing to notice
is the worker failing with `relation "processing_jobs" does not exist` --
which is what it did on the development database here.

So a new migration goes at the end of the chain, always. The end is the only
place every database, however old, is guaranteed to pass through.

`_has_table` makes this safe either way: a database that already ran this as
021 finds the table present and this becomes a no-op.

Revision ID: 030
Revises: 029
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "030"
down_revision: Union[str, None] = "029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "processing_jobs"
CLAIM_INDEX = "ix_processing_jobs_claim"


def _has_table() -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(TABLE)


def upgrade() -> None:
    if _has_table():
        return

    op.create_table(
        TABLE,
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "upload_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sensor_data_uploads.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column(
            "job_type",
            sa.String(40),
            nullable=False,
            server_default="measurement_pipeline",
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued", index=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "available_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
            index=True,
        ),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )

    # The claim query in crud/job.py reads exactly this.
    op.create_index(
        CLAIM_INDEX,
        TABLE,
        ["status", "available_at"],
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    if not _has_table():
        return
    op.drop_index(CLAIM_INDEX, table_name=TABLE)
    op.drop_table(TABLE)
