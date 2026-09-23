"""Learning a normal into a version, and reading how good it is — VIK-026/027.

`test_baseline_lifecycle` covers the states. This covers what happens to the
statistics as those states change, and the two questions a caller actually
asks: which baseline am I being compared against, and is it worth anything.

The failure this file exists to prevent: a stale row. A feature that
qualified for a baseline last month and no longer does -- the window moved,
the captures at the current acquisition shape fell below the floor -- must
lose its row rather than keep the old one. A reader cannot tell a stale
baseline from a current one, and will compare today's capture against a
normal learned from data that is no longer in the window.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from sqlalchemy import text

from app.ai.baseline import MIN_SAMPLES, PREFERRED_SAMPLES
from app.services import baseline_lifecycle as lc
from app.services.baseline_engine import (
    load_baseline_map,
    reset_baseline,
    roll_baseline,
)
from app.services.baseline_health import (
    LOW_CONFIDENCE,
    STALE_AFTER_DAYS,
    feature_health,
    sensor_health,
)

RATE = 25_000.0
SAMPLES = 20_000
CODES = ("rms", "peak", "crest_factor")


def add_captures(db, sensor_id, count, *, start_days_ago=40.0, channels=(0, 1),
                 codes=CODES, quality="high", rate=RATE, samples=SAMPLES,
                 seed=0, spread=0.001, centre=0.05):
    """Write `count` captures of feature history, one per hour.

    Real-shaped rather than minimal: the engine refuses a window whose
    values are nearly all identical, so a fixture that wrote the same number
    every time would test the refusal path and nothing else.
    """
    rng = np.random.default_rng(seed)
    first = datetime.now(timezone.utc) - timedelta(days=start_days_ago)
    upload_ids = []

    for i in range(count):
        when = first + timedelta(hours=i)
        upload_id = uuid.uuid4()
        upload_ids.append(upload_id)
        db.execute(text("""
            INSERT INTO sensor_data_uploads
                (id, sensor_id, channel_count, pdf_path, created_at)
            VALUES (:id, :s, :n, '', :t)
        """), {"id": str(upload_id), "s": str(sensor_id),
               "n": len(channels), "t": when})
        db.execute(text("""
            INSERT INTO raw_vibration_captures
                (upload_id, sensor_id, sample_rate_hz, sample_count,
                 channel_count, created_at)
            VALUES (:u, :s, :r, :n, :c, :t)
        """), {"u": str(upload_id), "s": str(sensor_id), "r": rate,
               "n": samples, "c": len(channels), "t": when})

        for channel in channels:
            if quality is not None:
                db.execute(text("""
                    INSERT INTO data_quality_assessments
                        (upload_id, sensor_id, channel, level,
                         confidence_factor, failed_checks, not_assessed,
                         checks, engine_version)
                    VALUES (:u, :s, :c, :l, 1.0, '[]'::jsonb, '[]'::jsonb,
                            '[]'::jsonb, '1')
                """), {"u": str(upload_id), "s": str(sensor_id),
                       "c": channel, "l": quality})
            for code in codes:
                db.execute(text("""
                    INSERT INTO measurement_channel_features
                        (id, upload_id, sensor_id, channel, feature_code,
                         value, unit, status, computed_at)
                    VALUES (:id, :u, :s, :c, :f, :v, 'g', 'normal', :t)
                """), {"id": str(uuid.uuid4()), "u": str(upload_id),
                       "s": str(sensor_id), "c": channel, "f": code,
                       "v": float(centre + spread * rng.normal()),
                       "t": when.replace(tzinfo=None)})
    db.flush()
    return upload_ids


# ------------------------------------------------- reset and roll ------

def test_a_reset_starts_a_new_version_and_leaves_the_old_one_alone(db, sensor_id):
    """The ticket's acceptance criterion. A finding recorded against v1 has
    to keep meaning what it meant after v2 exists."""
    add_captures(db, sensor_id, 20)
    first = reset_baseline(db, sensor_id, reason="initial")
    before = load_baseline_map(db, sensor_id, version=first["version"])
    assert before, "the first version should have learned something"

    second = reset_baseline(db, sensor_id, reason="after the rebuild")
    assert second["version"] == first["version"] + 1
    assert second["state"] == lc.ACTIVE

    after = load_baseline_map(db, sensor_id, version=first["version"])
    assert after.keys() == before.keys()
    for key, row in before.items():
        assert after[key]["median"] == row["median"], (
            "the retired version's statistics must not have moved"
        )


def test_a_roll_stays_on_the_same_version(db, sensor_id):
    add_captures(db, sensor_id, 20)
    first = reset_baseline(db, sensor_id, reason="initial")
    rolled = roll_baseline(db, sensor_id)
    assert rolled["version"] == first["version"]
    assert len(lc.history(db, sensor_id)) == 1


def test_a_roll_folds_in_captures_that_arrived_since(db, sensor_id):
    add_captures(db, sensor_id, 20, centre=0.05, spread=0.001, seed=1)
    reset_baseline(db, sensor_id, reason="initial")
    before = load_baseline_map(db, sensor_id)[(0, "rms")]["median"]

    add_captures(db, sensor_id, 20, start_days_ago=5.0, centre=0.20,
                 spread=0.001, seed=2)
    roll_baseline(db, sensor_id)
    after = load_baseline_map(db, sensor_id)[(0, "rms")]["median"]

    assert after > before, "a roll that ignored new captures would not be a roll"


def test_a_roll_removes_a_feature_that_no_longer_qualifies(db, sensor_id):
    """A stale row is worse than a missing one: a reader cannot tell it is
    stale, and will compare today's capture against a normal learned from
    data no longer in the window."""
    add_captures(db, sensor_id, 20, codes=("rms", "peak"))
    reset_baseline(db, sensor_id, reason="initial")
    assert (0, "peak") in load_baseline_map(db, sensor_id)

    db.execute(text("DELETE FROM measurement_channel_features "
                    " WHERE sensor_id = :s AND feature_code = 'peak'"),
               {"s": str(sensor_id)})
    roll_baseline(db, sensor_id)

    current = load_baseline_map(db, sensor_id)
    assert (0, "rms") in current
    assert (0, "peak") not in current, (
        "the feature has no history left, so it must have no baseline"
    )


def test_a_frozen_baseline_does_not_roll(db, sensor_id):
    add_captures(db, sensor_id, 20, centre=0.05, seed=1)
    reset_baseline(db, sensor_id, reason="initial")
    pinned = load_baseline_map(db, sensor_id)[(0, "rms")]["median"]
    lc.freeze(db, sensor_id, reason="known good")

    add_captures(db, sensor_id, 20, start_days_ago=5.0, centre=0.20, seed=2)
    with pytest.raises(lc.LifecycleError):
        roll_baseline(db, sensor_id)

    assert load_baseline_map(db, sensor_id)[(0, "rms")]["median"] == pinned, (
        "a refused roll must not have written anything"
    )


def test_a_reset_that_learns_nothing_does_not_retire_a_working_baseline(db, sensor_id):
    """Activating an empty version would leave the sensor with no learned
    normal at all -- strictly worse than the baseline it replaced."""
    add_captures(db, sensor_id, 20)
    first = reset_baseline(db, sensor_id, reason="initial")

    db.execute(text("DELETE FROM measurement_channel_features WHERE sensor_id = :s"),
               {"s": str(sensor_id)})
    second = reset_baseline(db, sensor_id, reason="nothing left to learn from")

    assert second["stored"] == 0
    assert lc.in_force(db, sensor_id)["version"] == first["version"]
    assert load_baseline_map(db, sensor_id), (
        "the working baseline must still be in force"
    )


def test_too_little_history_produces_no_baseline_rather_than_a_weak_one(db, sensor_id):
    """A baseline built from four captures is worse than none, because the
    system then trusts it."""
    add_captures(db, sensor_id, MIN_SAMPLES - 1)
    result = reset_baseline(db, sensor_id, reason="too early")
    assert result["stored"] == 0
    assert load_baseline_map(db, sensor_id) == {}


def test_reading_without_a_version_returns_nothing_when_none_is_in_force(db, sensor_id):
    """Not the newest rows lying about. A version left in `building` was
    deliberately not activated, and using it anyway defeats the point."""
    add_captures(db, sensor_id, 20)
    reset_baseline(db, sensor_id, reason="built only", activate=False)
    assert load_baseline_map(db, sensor_id) == {}
    assert lc.in_force(db, sensor_id) is None


# ------------------------------------------------- baseline health -----

def test_health_says_unavailable_when_nothing_is_in_force(db, sensor_id):
    health = sensor_health(db, sensor_id)
    assert health["available"] is False
    assert "No baseline is in force" in health["reason"]
    # Same shape either way, so a caller never branches on the response
    # structure to find out whether there is a baseline.
    for key in ("coverage", "confidence", "samples", "freshness",
                "exclusions", "warnings", "history"):
        assert key in health


def test_health_reports_what_the_baseline_was_built_from(db, sensor_id):
    add_captures(db, sensor_id, 20, channels=(0, 1), codes=CODES)
    reset_baseline(db, sensor_id, reason="initial")

    health = sensor_health(db, sensor_id, expected_feature_count=len(CODES))
    assert health["available"] is True
    assert health["version"]["state"] == lc.ACTIVE
    assert health["coverage"]["rows"] == len(CODES) * 2
    assert health["coverage"]["channels"] == [0, 1]
    assert health["coverage"]["fraction"] == 1.0
    assert health["samples"]["median"] == 20
    assert health["samples"]["minimum_required"] == MIN_SAMPLES
    assert health["samples"]["preferred"] == PREFERRED_SAMPLES


def test_a_thin_baseline_says_so(db, sensor_id):
    """Available and worth very little is a state the read model has to be
    able to express, or the platform repeats the mistake it started with."""
    add_captures(db, sensor_id, MIN_SAMPLES + 1)
    reset_baseline(db, sensor_id, reason="thin")

    health = sensor_health(db, sensor_id)
    assert health["available"] is True
    assert health["samples"]["below_preferred_rows"] > 0
    assert any("at the median" in w for w in health["warnings"])


def test_a_stale_window_says_so(db, sensor_id):
    add_captures(db, sensor_id, 20, start_days_ago=STALE_AFTER_DAYS + 40)
    reset_baseline(db, sensor_id, reason="old")

    health = sensor_health(db, sensor_id)
    assert health["freshness"]["stale"] is True
    assert health["freshness"]["age_days"] > STALE_AFTER_DAYS
    assert any("describes the machine as it was" in w
               for w in health["warnings"])


def test_a_window_the_sensor_has_outgrown_says_so(db, sensor_id):
    add_captures(db, sensor_id, 20, start_days_ago=60.0, seed=1)
    reset_baseline(db, sensor_id, reason="initial")
    # More captures arrive than the baseline was built from, and it is not
    # rolled. Counted rather than timed: a busy sensor leaves a baseline
    # behind in a week, a quiet one keeps a three-month window current.
    add_captures(db, sensor_id, 40, start_days_ago=5.0, seed=2)

    health = sensor_health(db, sensor_id)
    assert health["freshness"]["captures_since_window"] == 40
    assert health["freshness"]["outgrown"] is True
    assert any("since the window closed" in w for w in health["warnings"])


def test_a_frozen_baseline_says_it_is_no_longer_learning(db, sensor_id):
    add_captures(db, sensor_id, 20)
    reset_baseline(db, sensor_id, reason="initial")
    lc.freeze(db, sensor_id, reason="known good")

    health = sensor_health(db, sensor_id)
    assert health["version"]["state"] == lc.FROZEN
    assert any("no longer learning" in w for w in health["warnings"])


def test_invalid_captures_are_excluded_and_the_exclusion_is_reported(db, sensor_id):
    """A clipped or dead channel is not a description of the machine. The
    count travels with the answer, because a baseline built after throwing
    half the window away is a different thing from one that kept it."""
    add_captures(db, sensor_id, 20, seed=1)
    add_captures(db, sensor_id, 6, start_days_ago=3.0, quality="invalid",
                 centre=5.0, seed=2)
    reset_baseline(db, sensor_id, reason="initial")

    health = sensor_health(db, sensor_id)
    assert health["exclusions"]["quality_excluded_observations"] > 0
    assert any("called the capture" in w for w in health["warnings"])
    # And the excluded values must not have moved the normal.
    assert load_baseline_map(db, sensor_id)[(0, "rms")]["median"] < 1.0


def test_a_feature_with_no_baseline_is_unavailable_not_normal(db, sensor_id):
    """The distinction the whole platform rests on. "No baseline" scored as
    normal is how a machine nobody has a normal for reads as healthy."""
    add_captures(db, sensor_id, 20, codes=("rms",))
    reset_baseline(db, sensor_id, reason="initial")

    known = feature_health(db, sensor_id, 0, "rms")
    assert known["available"] is True
    assert known["sample_count"] == 20

    unknown = feature_health(db, sensor_id, 0, "spectral_entropy")
    assert unknown["available"] is False
    assert "not the same as normal" in unknown["reason"]


def test_health_reads_the_version_in_force_not_the_newest(db, sensor_id):
    """A version left in `building` must not be reported on: nothing is
    being judged against it."""
    add_captures(db, sensor_id, 20)
    first = reset_baseline(db, sensor_id, reason="initial")
    reset_baseline(db, sensor_id, reason="built only", activate=False)

    health = sensor_health(db, sensor_id)
    assert health["version"]["version"] == first["version"]
    assert health["version"]["state"] == lc.ACTIVE


def test_history_travels_with_the_answer(db, sensor_id):
    """So a finding pointing at v1 can be explained after v3 is in force."""
    add_captures(db, sensor_id, 20)
    reset_baseline(db, sensor_id, reason="first")
    reset_baseline(db, sensor_id, reason="second")

    health = sensor_health(db, sensor_id)
    assert [v["version"] for v in health["history"]] == [2, 1]
    assert health["history"][1]["state"] == lc.SUPERSEDED
    assert health["history"][1]["reason"] == "first"


def test_a_mixed_population_is_low_confidence_at_exactly_the_threshold(db, sensor_id):
    """The engine halves confidence to 0.5 for a window holding more than
    one population. A "low confidence" test written as strictly-below would
    exclude the one case it exists for, and flag nothing on real data."""
    add_captures(db, sensor_id, 30, centre=0.05, spread=0.001, seed=1)
    # A minority from somewhere else: admitted by quality, far enough out
    # that the percentiles stop describing the same machine as the median.
    add_captures(db, sensor_id, 3, start_days_ago=8.0, centre=5.0,
                 spread=0.01, seed=2)
    reset_baseline(db, sensor_id, reason="contaminated")

    health = sensor_health(db, sensor_id)
    assert health["exclusions"]["mixed_population_rows"] > 0
    assert health["confidence"]["min"] == pytest.approx(LOW_CONFIDENCE)
    assert health["confidence"]["low_confidence_rows"] > 0, (
        "a confidence of exactly the threshold is low confidence"
    )
    assert any("at or below" in w for w in health["warnings"])


def test_outgrown_is_judged_against_the_typical_feature(db, sensor_id):
    """One feature with a long history must not suppress the flag for the
    rest. Here rms has 60 captures behind it and the others have 20, and 30
    new captures have arrived -- which leaves most of the baseline behind."""
    add_captures(db, sensor_id, 40, start_days_ago=90.0, codes=("rms",), seed=1)
    add_captures(db, sensor_id, 20, start_days_ago=60.0, codes=CODES, seed=2)
    reset_baseline(db, sensor_id, reason="uneven history")

    counts = sorted(r["sample_count"]
                    for r in load_baseline_map(db, sensor_id).values())
    assert counts[0] == 20 and counts[-1] == 60, (
        "the fixture must actually produce an uneven history"
    )

    add_captures(db, sensor_id, 30, start_days_ago=2.0, codes=CODES, seed=3)
    health = sensor_health(db, sensor_id)
    assert health["freshness"]["captures_since_window"] == 30
    assert health["freshness"]["outgrown"] is True


def test_a_built_but_unactivated_baseline_is_not_reported_as_the_answer(db, sensor_id):
    """A version in `building` holds real statistics, so it is tempting to
    fall back to it when nothing is in force. It must not be: nobody
    activated it, which means nobody has looked at what it learned, and
    reporting it would make the review step that `building` exists for
    invisible."""
    add_captures(db, sensor_id, 20)
    built = reset_baseline(db, sensor_id, reason="built only", activate=False)
    assert built["stored"] > 0, "the fixture must produce a real version"
    assert lc.get_version(db, sensor_id, built["version"])["state"] == lc.BUILDING

    health = sensor_health(db, sensor_id)
    assert health["available"] is False
    assert "never activated" in health["reason"]
    # It still appears in the history, because it exists and somebody has to
    # be able to see that it is waiting.
    assert [v["version"] for v in health["history"]] == [built["version"]]
