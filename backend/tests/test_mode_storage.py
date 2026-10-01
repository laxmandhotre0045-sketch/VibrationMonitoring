"""Deciding and recording a capture's operating mode — VIK-039 storage.

Two small functions feed the detector, and both were untested until
mutation testing said so. They matter more than their size suggests: one
decides whether the machine was running at all, and the other decides
whether its speed held steady. Get either wrong and the mode is wrong, and
the mode decides which baseline the capture joins.
"""

from __future__ import annotations

import numpy as np
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.services.mode_storage import overall_level, stability_from_quality


# ----------------------------------------------- the level --------------

def signal(sigma, n=2000, offset=0.0, seed=0):
    rng = np.random.default_rng(seed)
    return (offset + rng.normal(0.0, sigma, n)).tolist()


def test_the_level_is_the_median_channel_not_the_mean():
    """One dead or clipped channel must not decide whether the machine is
    running. On this gateway the healthy channels already differ by six
    times between quietest and loudest, so a mean is pulled about by the
    loudest one before any fault exists."""
    channels = {f"ch{i}": signal(0.002, seed=i) for i in range(7)}
    channels["ch7"] = signal(0.5, seed=99)          # one very loud channel

    level = overall_level(channels)
    values = [float(np.std(v)) for v in channels.values()]

    assert level == pytest.approx(float(np.median(values)), rel=0.01)
    assert level < float(np.mean(values)) / 2, (
        "the mean is dragged up by the loud channel; the median is not"
    )


def test_the_level_ignores_a_standing_offset():
    """A channel sitting on a bias is not a channel that is vibrating. This
    is the same mistake that once made eight of thirteen time features
    report the sensor's resting position as vibration."""
    moving = {"ch0": signal(0.01, offset=0.0, seed=1)}
    offset = {"ch0": signal(0.01, offset=5.0, seed=1)}
    assert overall_level(moving) == pytest.approx(overall_level(offset), rel=1e-6)


def test_no_channels_means_no_level():
    assert overall_level({}) is None
    assert overall_level({"ch0": []}) is None


# ------------------------------------------- the steadiness verdict -----

def quality(*checks):
    return {"channels": {0: {"checks": list(checks)}}}


def check(name="unstable_speed", passed=True, applicable=True):
    return {"check": name, "passed": passed, "applicable": applicable}


def test_a_speed_that_held_is_steady():
    assert stability_from_quality(quality(check(passed=True))) == "steady"


def test_a_speed_that_moved_is_unstable():
    assert stability_from_quality(quality(check(passed=False))) == "unstable"


def test_a_check_that_could_not_run_is_not_steady():
    """The steadiness check stands down on records too short to judge -- at
    this pump's capture length each half holds 9.87 shaft revolutions
    against the 10 it needs. Reporting that as steady would let a capture
    taken during a speed change into a baseline that assumes one speed."""
    assert stability_from_quality(quality(check(applicable=False))) is None


def test_nothing_assessed_is_not_steady():
    """None and 'steady' are different facts. Only one of them is evidence."""
    assert stability_from_quality(None) is None
    assert stability_from_quality({"channels": {}}) is None
    assert stability_from_quality(quality(check(name="clipping"))) is None


def test_one_unstable_channel_makes_the_capture_unstable():
    """The speed is a property of the shaft, not of a transducer. If any
    channel saw it move, it moved."""
    summary = {"channels": {
        0: {"checks": [check(passed=True)]},
        1: {"checks": [check(passed=False)]},
    }}
    assert stability_from_quality(summary) == "unstable"


# --------------------------------- what the database refuses ------------

def test_a_capture_cannot_be_both_unknown_and_in_a_mode(db, sensor_id):
    """Enforced by a check constraint, which is why the history query can
    trust `is_unknown`. A row claiming both is a state every reader would
    resolve differently."""
    import uuid

    upload_id = uuid.uuid4()
    db.execute(text("""
        INSERT INTO sensor_data_uploads (id, sensor_id, channel_count, pdf_path)
        VALUES (:id, :s, 8, '')
    """), {"id": str(upload_id), "s": str(sensor_id)})

    equipment = db.execute(text(
        "SELECT equipment_id FROM sensor_configurations WHERE id = :s"),
        {"s": str(sensor_id)}).scalar()
    mode_id = db.execute(text("""
        INSERT INTO operating_modes (equipment_id, label, rpm_min, rpm_max)
        VALUES (:e, 'normal_running', 1400, 1600) RETURNING id
    """), {"e": str(equipment)}).scalar()

    with pytest.raises(IntegrityError):
        db.execute(text("""
            INSERT INTO capture_operating_modes
                (upload_id, sensor_id, mode_id, label, is_unknown, confidence)
            VALUES (:u, :s, :m, 'normal_running', true, 1.0)
        """), {"u": str(upload_id), "s": str(sensor_id), "m": str(mode_id)})
        db.flush()
