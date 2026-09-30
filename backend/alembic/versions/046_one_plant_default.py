"""One plant-wide settings row, not several — a fix to 045.

Revision ID: 046
Revises: 045

045 put a unique constraint on `equipment_id` and used `ON CONFLICT
(equipment_id)` to update in place. That works for a machine's own row and
silently does not for the plant-wide one, because Postgres treats NULLs as
distinct in a unique index: two rows with a NULL equipment_id do not
conflict, so every edit to the plant default inserted another one instead
of updating it.

Nothing errored. `settings_for` then returned whichever of the duplicates
the planner happened to reach first, so changing a plant-wide setting
appeared to do nothing about half the time -- and the half it worked would
have been the more confusing outcome.

A partial unique index on `equipment_id IS NULL` gives the NULL row the
uniqueness the constraint was meant to provide, and the service targets it
by a separate UPDATE rather than by ON CONFLICT.
"""

from alembic import op
import sqlalchemy as sa

revision = "046"
down_revision = "045"
branch_labels = None
depends_on = None

TABLE = "ai_general_settings"


def upgrade() -> None:
    # Collapse any duplicates the flaw already allowed, keeping the most
    # recently updated -- that is the edit somebody last intended.
    op.execute(f"""
        DELETE FROM {TABLE} a
         USING {TABLE} b
         WHERE a.equipment_id IS NULL
           AND b.equipment_id IS NULL
           AND a.updated_at < b.updated_at
    """)
    op.execute(f"""
        DELETE FROM {TABLE} a
         USING {TABLE} b
         WHERE a.equipment_id IS NULL
           AND b.equipment_id IS NULL
           AND a.updated_at = b.updated_at
           AND a.id < b.id
    """)

    op.create_index(f"uq_{TABLE}_plant_default", TABLE, ["equipment_id"],
                    unique=True,
                    postgresql_where=sa.text("equipment_id IS NULL"))


def downgrade() -> None:
    op.drop_index(f"uq_{TABLE}_plant_default", table_name=TABLE)
