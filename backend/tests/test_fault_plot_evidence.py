"""The fault-to-plot mapping, as stored — VIK-059.

The ticket asks for a table rather than code, and is right to: which plot
shows a fault is reference material an analyst should be able to correct
without a deploy. That choice moves two failure modes into the database,
and these tests are what stand in front of them.

**A row can name a fault the rule table does not have.** Nothing in
Postgres knows what `vibcore.signatures` contains, so a key that drifts --
`looseness` where the rule is `mechanical_looseness` -- produces an empty
panel rather than an error. Every fault key in the seed was wrong the first
time this was written, and only a check against the rule table found it.

**A row can name a plot the frontend does not render.** That sends somebody
looking for a screen nobody built, which is worse than no guidance at all.
The column has a check constraint; this proves it bites.
"""

from __future__ import annotations

import json
import os

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.usefixtures("db")

VIBCORE_RULES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "vibcore", "data", "fault_signatures.json")

#: What `app.schemas.measurement.PLOT_TYPES` offers, which is what the
#: frontend renders.
RENDERED = {"time_waveform", "circular_time_waveform", "fft_spectrum",
            "envelope_spectrum", "envelope_waveform", "trend_plot"}


def rule_keys() -> set[str]:
    with open(VIBCORE_RULES, encoding="utf-8") as handle:
        return set(json.load(handle)["rules"])


def rows(db):
    return [dict(r) for r in db.execute(text("""
        SELECT fault_key, plot_type, rank, what_to_look_for, why_this_plot
          FROM fault_plot_evidence ORDER BY fault_key, rank
    """)).mappings().fetchall()]


def test_the_mapping_was_seeded(db):
    assert len(rows(db)) >= 30


def test_every_fault_in_the_rule_table_has_somewhere_to_look(db):
    """A finding with no plot guidance is a finding whose evidence the
    reader has to go and find for themselves."""
    mapped = {r["fault_key"] for r in rows(db)}
    missing = rule_keys() - mapped
    assert not missing, f"no plot guidance for {sorted(missing)}"


def test_no_row_names_a_fault_the_engine_cannot_produce(db):
    """The mistake this table invites. Every key in the first draft of the
    seed was invented -- `looseness`, `cavitation`, `electrical_fault` --
    and each would have rendered as an empty panel, silently."""
    mapped = {r["fault_key"] for r in rows(db)}
    invented = mapped - rule_keys()
    assert not invented, (
        f"{sorted(invented)} are not in vibcore's rule table, so no finding "
        f"will ever carry these keys and the rows are unreachable")


def test_no_row_names_a_plot_the_frontend_does_not_render(db):
    named = {r["plot_type"] for r in rows(db)}
    assert named <= RENDERED, f"{sorted(named - RENDERED)} do not exist"


def test_the_plot_type_constraint_actually_bites(db):
    """The check constraint is the only thing standing between a typo and
    an analyst hunting for a screen nobody built."""
    with pytest.raises(Exception):
        db.execute(text("""
            INSERT INTO fault_plot_evidence
                (fault_key, plot_type, rank, what_to_look_for, why_this_plot)
            VALUES ('unbalance', 'waterfall_plot', 1, 'x', 'y')
        """))
        db.flush()
    db.rollback()


def test_a_fault_cannot_list_the_same_plot_twice(db):
    with pytest.raises(Exception):
        db.execute(text("""
            INSERT INTO fault_plot_evidence
                (fault_key, plot_type, rank, what_to_look_for, why_this_plot)
            VALUES ('unbalance', 'fft_spectrum', 9, 'x', 'y')
        """))
        db.flush()
    db.rollback()


def test_every_fault_has_a_first_plot_to_open(db):
    """Rank exists so a reader is told where to start, not handed three
    equal options."""
    ranked: dict[str, list[int]] = {}
    for row in rows(db):
        ranked.setdefault(row["fault_key"], []).append(row["rank"])

    for key, values in ranked.items():
        assert sorted(values) == list(range(1, len(values) + 1)), (
            f"{key} has ranks {sorted(values)}, which names no clear first "
            f"plot or skips a number")


def test_every_row_says_what_to_look_for_and_why_that_plot(db):
    """Without the why, the table is a lookup nobody can argue with -- the
    failure mode of this whole phase, in miniature."""
    for row in rows(db):
        where = f"{row['fault_key']}/{row['plot_type']}"
        assert len(row["what_to_look_for"]) > 20, where
        assert len(row["why_this_plot"]) > 40, where


def test_bearing_faults_send_you_to_the_envelope_first(db):
    """The one piece of guidance most worth getting right: a bearing impact
    is a high-frequency ring modulated at the defect rate, so the ordinary
    spectrum shows the ringing and buries the rate."""
    for key in ("bearing_outer_race", "bearing_inner_race",
                "bearing_ball_defect", "bearing_cage"):
        first = [r for r in rows(db)
                 if r["fault_key"] == key and r["rank"] == 1]
        assert first, f"{key} has no first plot"
        assert first[0]["plot_type"] == "envelope_spectrum", key


def test_findings_can_store_symptoms(db):
    """VIK-051's column. Defaulted to an empty list rather than nullable:
    an existing finding predates symptom detection, and NULL would read as
    "none present" where the truth is "none recorded"."""
    column = db.execute(text("""
        SELECT is_nullable, column_default FROM information_schema.columns
         WHERE table_name = 'fault_findings' AND column_name = 'symptoms'
    """)).mappings().fetchone()

    assert column is not None, "migration 038 did not add the column"
    assert column["is_nullable"] == "NO"
    assert "[]" in (column["column_default"] or "")
