"""Definitions and defaults for the ten envelope features — VIK-020.

Revision ID: 024
Revises: 023

measurement_channel_features has a foreign key onto feature_definitions, so
without this the envelope features cannot be stored at all -- the extractor
produces them and the insert is rejected. That constraint is doing its job:
it caught exactly this the first time a real capture was recomputed.

The rows themselves come from app/services/feature_catalog.py, which 023
established as the single source of truth. This migration calls the same
sync, so it carries no copy of the data and a future feature group needs a
migration of the same three lines.
"""

from alembic import op

from app.services.feature_catalog import sync_to_database

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None

#: The codes this revision introduces. Named here rather than derived, so the
#: downgrade removes what this migration added and not whatever the catalogue
#: happens to hold by then.
ENVELOPE_CODES = (
    "ftf_band_energy", "bsf_band_energy", "bpfo_band_energy", "bpfi_band_energy",
    "bearing_harmonic_energy", "envelope_peak", "envelope_kurtosis",
    "demodulated_peak_prominence", "repetition_impact_frequency",
    "resonance_band_energy",
)


def upgrade() -> None:
    definitions, rules = sync_to_database(op.get_bind())
    print(f"feature catalogue synced: {definitions} definitions, {rules} new rules")


def downgrade() -> None:
    import sqlalchemy as sa

    bind = op.get_bind()
    codes = list(ENVELOPE_CODES)
    # Features first: they reference the definitions.
    bind.execute(sa.text(
        "DELETE FROM measurement_channel_features WHERE feature_code = ANY(:c)"),
        {"c": codes})
    bind.execute(sa.text(
        "DELETE FROM measurement_channel_feature_trends WHERE feature_code = ANY(:c)"),
        {"c": codes})
    bind.execute(sa.text(
        "DELETE FROM feature_threshold_rules WHERE feature_code = ANY(:c)"), {"c": codes})
    bind.execute(sa.text(
        "DELETE FROM feature_definitions WHERE code = ANY(:c)"), {"c": codes})
