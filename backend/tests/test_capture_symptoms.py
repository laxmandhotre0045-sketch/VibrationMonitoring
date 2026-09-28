"""Symptoms must survive the shaft-speed gate — VIK-051.

`persist_findings` returns early when no shaft speed could be established,
and it is right to: every rule in the table is written in orders, and an
order computed against a guessed speed is wrong by the ratio of the guess.

The first version detected symptoms inside the per-channel ranking loop,
which is *after* that return. Reprocessing a real capture is what found it:
the layer had run zero times in production, because no capture from this
gateway has ever established a shaft speed. The one machine the feature was
meant to help was the one machine it could not run on.

These tests fix the ordering in place. Two of them would have caught the
original bug; the rest cover the honesty the table is there to provide --
an empty symptom list from a capture that could run two checks means
something different from an empty list from one that could run five.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.services.fault_storage import (
    SYMPTOM_CHECKS_TOTAL,
    SYMPTOM_CHECKS_WITHOUT_SPEED,
)


def test_the_table_exists_with_one_row_per_channel_per_capture(db):
    """Reprocessing must update a channel's row, not add a second."""
    constraint = db.execute(text("""
        SELECT COUNT(*) FROM information_schema.table_constraints
         WHERE table_name = 'capture_symptoms'
           AND constraint_type = 'UNIQUE'
    """)).scalar()
    assert constraint >= 1


def test_a_row_records_how_many_checks_could_run(db):
    """The column that stops an empty list being read as a quiet machine."""
    columns = {row[0] for row in db.execute(text("""
        SELECT column_name FROM information_schema.columns
         WHERE table_name = 'capture_symptoms'
    """)).fetchall()}

    assert {"shaft_usable", "checks_run", "checks_possible"} <= columns


def test_without_a_shaft_speed_fewer_checks_are_possible(db):
    """Three of the five checks are written in orders of running speed and
    cannot be evaluated without one. Reporting five out of five on a
    capture that could only run two would overstate the search."""
    assert SYMPTOM_CHECKS_WITHOUT_SPEED < SYMPTOM_CHECKS_TOTAL
    assert SYMPTOM_CHECKS_TOTAL == 5


def test_checks_run_can_never_exceed_checks_possible(db):
    """A constraint rather than a convention: the two are written by
    different branches and drifting apart would be invisible."""
    with pytest.raises(Exception):
        db.execute(text("""
            INSERT INTO capture_symptoms
                (upload_id, sensor_id, channel, checks_run, checks_possible)
            VALUES (gen_random_uuid(), gen_random_uuid(), 0, 5, 2)
        """))
        db.flush()
    db.rollback()


def test_symptoms_default_to_an_empty_list_not_null(db):
    """NULL reads as "none present"; the truth for an older row is "none
    recorded", and the two are opposite claims."""
    column = db.execute(text("""
        SELECT is_nullable, column_default FROM information_schema.columns
         WHERE table_name = 'capture_symptoms' AND column_name = 'symptoms'
    """)).mappings().fetchone()

    assert column["is_nullable"] == "NO"
    assert "[]" in (column["column_default"] or "")


def test_detection_happens_before_the_shaft_speed_gate(db):
    """The regression guard, read off the source.

    A behavioural test would need a full capture through the pipeline; what
    actually went wrong was an ordering mistake in one function, and the
    order of those two statements is the whole fix.
    """
    import inspect

    from app.services import fault_storage

    source = inspect.getsource(fault_storage.persist_findings)
    detect_at = source.index("_record_symptoms(")
    gate_at = source.index("if not shaft_usable:")

    assert detect_at < gate_at, (
        "symptom detection moved back behind the shaft-speed early return. "
        "No capture from this gateway establishes a shaft speed, so the "
        "whole symptom layer stops running in production -- silently, "
        "because an empty table looks the same as a quiet machine.")
