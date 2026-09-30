"""The model registry — section 22.

Revision ID: 044
Revises: 043

Section 22 lists nine things that must be stored and ends with the line
that gives them their point: "No model should be changed silently without
version tracking."

Three of the nine already existed -- baseline versions, analyst feedback
history, and an `engine_version` stamped on five tables. But five modules
each declaring their own `ENGINE_VERSION = "1"` is five places to forget,
and nothing anywhere recorded *what* a version meant, when it came into
force, what data it was built from, or how well it performed. A version
number nobody can look up is a string.

**This table is the record, and `app.ai.versions` is the declaration.** A
test checks one against the other, so bumping a version without registering
what changed fails the suite. That is deliberately the same shape as the
released-revisions manifest that guards the migration chain: both protect a
promise about history, and no amount of inspecting the current state can
verify one of those.

**Rollback is a row, not a delete.** Superseding a version records what it
was replaced by and leaves the old row in place, because the rows it
stamped are still in the database and still need explaining.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None

TABLE = "model_versions"

#: The components as `app.ai.versions` declares them at the time of this
#: migration. Seeded so the registry is populated on day one rather than
#: starting empty and failing its own guard.
SEED = (
    ("feature_extraction", "Feature extraction", "1",
     "every row in measurement_channel_features"),
    ("processing", "Signal processing", "1",
     "the spectra and envelopes features are computed from"),
    ("quality", "Data quality", "1", "data_quality_assessments"),
    ("operating_mode", "Operating mode detection", "1",
     "capture_operating_modes"),
    ("anomaly", "Anomaly scoring", "1", "feature_anomaly_scores"),
    ("detectors", "Joint detectors", "1", "capture_detector_scores"),
    ("fault", "Fault diagnosis", "1", "fault_findings"),
)


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("component", sa.String(64), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("stamps", sa.Text(), nullable=True),

        # Section 22's "training date" and "training data period". Null for
        # a rule-based component, which is not a gap -- a rule table was
        # written rather than trained, and recording a training date for it
        # would be fiction.
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("training_period_start", sa.DateTime(timezone=True),
                  nullable=True),
        sa.Column("training_period_end", sa.DateTime(timezone=True),
                  nullable=True),
        sa.Column("trained_on_captures", sa.Integer(), nullable=True),

        # Section 22's "model performance". Measured from analyst feedback
        # where there is any, and null until then -- a model nobody has
        # judged has no measured performance, which is different from
        # performing badly.
        sa.Column("performance", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),

        # What changed, in words. The reason a version number is worth
        # having at all.
        sa.Column("notes", sa.Text(), nullable=True),

        sa.Column("effective_from", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        # Section 22's "rollback option": superseding records the successor
        # and leaves the row, because the data it stamped is still stored.
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_by", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_unique_constraint(
        f"uq_{TABLE}_component_version", TABLE, ["component", "version"])
    op.create_index(f"ix_{TABLE}_component", TABLE,
                    ["component", "effective_from"])
    # A superseded version must say what replaced it, or the rollback path
    # is a dead end.
    op.create_check_constraint(
        f"ck_{TABLE}_superseded_names_successor", TABLE,
        "superseded_at IS NULL OR superseded_by IS NOT NULL")
    op.create_check_constraint(
        f"ck_{TABLE}_training_period", TABLE,
        "training_period_start IS NULL OR training_period_end IS NULL "
        "OR training_period_end >= training_period_start")

    op.bulk_insert(
        sa.table(TABLE,
                 sa.column("component", sa.String),
                 sa.column("name", sa.String),
                 sa.column("version", sa.String),
                 sa.column("stamps", sa.Text),
                 sa.column("notes", sa.Text)),
        [{"component": key, "name": name, "version": version,
          "stamps": stamps,
          "notes": "Initial registered version. Every component was already "
                   "running at this version before the registry existed; "
                   "this records it rather than claiming it is new."}
         for key, name, version, stamps in SEED])


def downgrade() -> None:
    op.drop_table(TABLE)
