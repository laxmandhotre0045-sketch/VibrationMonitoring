"""Section 4.1's switches and filter settings.

Revision ID: 045
Revises: 044

Section 4.1 lists nineteen things a user should be able to configure.
Fourteen were: the acquisition settings live on `plot_configurations`, the
limits on `feature_threshold_rules`, and the sensitivity profile on
`ai_sensitivity_settings`. Five were not, and they fall into two groups.

**Three on/off switches: mode detection, auto fault detection, auto
reports.** Every one of these currently runs unconditionally. That sounds
harmless and is not: a machine being commissioned, or one running a test
regime, generates findings that are true of a machine nobody is trying to
diagnose, and they go into the same baselines and the same queue as
everything else. Without a switch the only way to stop that is to stop
ingesting, which loses the data too.

**Two acquisition details: filter settings and the envelope band.** Both
were fixed in code. The envelope band in particular is not a universal
constant -- it should sit on the resonance the bearing actually rings at,
which differs per machine and per mounting, and a band chosen for one pump
demodulates the wrong part of the spectrum on another.

Every switch defaults to on and every band to what the code already used,
so nothing changes behaviour until somebody deliberately changes it. A
migration that silently turned a running engine off would be a worse fault
than the gap it closes.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "045"
down_revision = "044"
branch_labels = None
depends_on = None

TABLE = "ai_general_settings"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        # Null means the plant-wide default. A row with an equipment_id
        # overrides it for that machine, which is how a single machine gets
        # taken out of diagnosis during commissioning without touching the
        # rest of the plant.
        sa.Column("equipment_id", postgresql.UUID(as_uuid=True),
                  nullable=True, unique=True),

        # The three switches. Default true throughout: this migration must
        # not change what any engine does.
        sa.Column("mode_detection_enabled", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("fault_detection_enabled", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("auto_reports_enabled", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),

        # Section 4.1's filter settings. Nulls mean "as the code does it
        # now" rather than "no filtering", so an unconfigured machine keeps
        # exactly the behaviour it had.
        sa.Column("highpass_hz", sa.Float(), nullable=True),
        sa.Column("lowpass_hz", sa.Float(), nullable=True),

        # The envelope demodulation band. Not a universal constant: it
        # should sit on the resonance the bearing actually rings at, which
        # differs per machine and per mounting.
        sa.Column("envelope_band_low_hz", sa.Float(), nullable=True),
        sa.Column("envelope_band_high_hz", sa.Float(), nullable=True),

        # Why somebody turned something off. A switch with no reason is
        # found six months later by a person who cannot tell whether it was
        # deliberate.
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.String(120), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    op.create_check_constraint(
        f"ck_{TABLE}_filter_order", TABLE,
        "highpass_hz IS NULL OR lowpass_hz IS NULL "
        "OR lowpass_hz > highpass_hz")
    op.create_check_constraint(
        f"ck_{TABLE}_envelope_order", TABLE,
        "envelope_band_low_hz IS NULL OR envelope_band_high_hz IS NULL "
        "OR envelope_band_high_hz > envelope_band_low_hz")
    # Turning an engine off is a decision somebody has to own.
    op.create_check_constraint(
        f"ck_{TABLE}_disabling_needs_a_reason", TABLE,
        "(mode_detection_enabled AND fault_detection_enabled "
        " AND auto_reports_enabled) OR notes IS NOT NULL")

    # The plant-wide default row, with everything on.
    op.execute(f"""
        INSERT INTO {TABLE} (equipment_id, notes)
        VALUES (NULL, 'Plant-wide defaults. Everything on, filters and '
                      'envelope band as the code already computed them.')
    """)


def downgrade() -> None:
    op.drop_table(TABLE)
