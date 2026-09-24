"""A definition and a default rule for every feature — VIK-021.

Revision ID: 023
Revises: 022

The extractor produces 36 features per channel. `feature_definitions` held
10, so the frontend could name and label fewer than a third of what the
platform measures; the rest arrived as bare codes with no unit and no
description, and `lib/vibration-features.ts` had nothing to render them from.

The ticket also notes that threshold_defaults.py duplicates this migration's
seed values and that the two are kept in step by hand, and asks for one
source of truth. That is now app/services/feature_catalog.py, and this
migration reads it rather than restating it.

Importing application code into a migration is usually a bad idea, because a
migration is a historical record and application code moves on. It is the
right trade here for one reason: the alternative is a second copy of 36 rows
that must be edited twice, which is the exact drift the ticket is about. The
seed is an idempotent upsert keyed on `code`, so re-running it after the
catalogue changes brings a database up to date rather than duplicating rows,
and no later migration has to restate any of it.

Existing rows are updated in place, not deleted and recreated: the ten that
already exist are referenced by feature_threshold_rules, and their ids are
worth keeping.
"""

import json

from alembic import op
import sqlalchemy as sa

from app.services.feature_catalog import all_default_rules, seed_rows

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None

DEFINITIONS = "feature_definitions"
RULES = "feature_threshold_rules"


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    for row in seed_rows():
        bind.execute(sa.text(f"""
            INSERT INTO {DEFINITIONS} (id, code, name, unit, description,
                                       sort_order, is_active)
            VALUES (gen_random_uuid(), :code, :name, :unit, :description,
                    :sort_order, :is_active)
            ON CONFLICT (code) DO UPDATE SET
                name        = EXCLUDED.name,
                unit        = EXCLUDED.unit,
                description = EXCLUDED.description,
                sort_order  = EXCLUDED.sort_order,
                is_active   = EXCLUDED.is_active
        """), row)

    # Rules are seeded only where the feature has none. A site that has tuned
    # a limit keeps it: overwriting someone's threshold with a factory value
    # during an upgrade is the kind of silent change that gets noticed as a
    # missed alarm weeks later.
    columns = _columns(RULES)
    scoped = [c for c in ("machine_type", "channel") if c in columns]
    # A rule with no machine type and no channel is the fleet-wide default.
    # Only those are seeded; a rule someone narrowed to one machine or one
    # channel is a deliberate act and is left alone.
    where_global = "".join(f" AND {c} IS NULL" for c in scoped)

    for code, rule in all_default_rules().items():
        exists = bind.execute(sa.text(
            f"SELECT 1 FROM {RULES} WHERE feature_code = :code{where_global} LIMIT 1"
        ), {"code": code}).fetchone()
        if exists:
            continue
        bind.execute(sa.text(f"""
            INSERT INTO {RULES} (id, feature_code, rule_type, normal_max,
                                 warning_max, normal_min, warning_min,
                                 metadata, is_active)
            VALUES (gen_random_uuid(), :code, :rule_type, :normal_max,
                    :warning_max, :normal_min, :warning_min,
                    CAST(:meta AS jsonb), true)
        """), {
            "code": code,
            "rule_type": rule.rule_type,
            "normal_max": rule.normal_max,
            "warning_max": rule.warning_max,
            "normal_min": rule.normal_min,
            "warning_min": rule.warning_min,
            "meta": json.dumps(rule.metadata or {}),
        })


def downgrade() -> None:
    """Remove only what this migration added.

    The ten definitions that predate it stay, with their original text
    restored is not attempted -- the descriptions here are supersets of the
    originals and no data depends on the wording. The 26 new ones and their
    rules go.
    """
    bind = op.get_bind()
    original = {
        "rms", "peak", "crest_factor", "kurtosis", "fft_band_energy_0_500",
        "amplitude_1x", "amplitude_2x", "amplitude_3x", "envelope_rms",
        "noise_floor",
    }
    added = [d["code"] for d in seed_rows() if d["code"] not in original]
    if not added:
        return
    bind.execute(sa.text(
        f"DELETE FROM {RULES} WHERE feature_code = ANY(:codes)"), {"codes": added})
    bind.execute(sa.text(
        f"DELETE FROM {DEFINITIONS} WHERE code = ANY(:codes)"), {"codes": added})
