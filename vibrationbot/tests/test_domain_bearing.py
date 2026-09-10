"""Known-answer tests for bearing fault frequencies.

The 6205 numbers are the most widely published values in the bearing-diagnosis
literature, which makes them a genuine external check rather than a snapshot of
whatever this code happens to produce.
"""

from __future__ import annotations

import math
import random

import pytest

from app.domain.bearing import (
    BearingGeometry,
    build_record,
    estimate_geometry,
    fault_frequencies,
    geometry_from_inputs,
    normalize_designation,
    resolve_bearing,
)

# SKF 6205-2RS: 9 balls, 7.94 mm ball, 39.04 mm pitch, 0 deg contact angle.
SKF_6205 = BearingGeometry(
    n_balls=9, ball_dia_mm=7.94, pitch_dia_mm=39.04, designation="6205"
)


def test_6205_known_answer_at_1750_rpm():
    freqs = fault_frequencies(SKF_6205, 1750)

    assert freqs.shaft_hz == pytest.approx(29.1667, abs=1e-3)
    assert freqs.bpfo_hz == pytest.approx(104.56, abs=0.05)
    assert freqs.bpfi_hz == pytest.approx(157.94, abs=0.05)
    assert freqs.bsf_hz == pytest.approx(68.75, abs=0.05)
    assert freqs.ftf_hz == pytest.approx(11.62, abs=0.05)


def test_6205_orders():
    freqs = fault_frequencies(SKF_6205, 1750)

    assert freqs.bpfo_order == pytest.approx(3.585, abs=0.002)
    assert freqs.bpfi_order == pytest.approx(5.415, abs=0.002)
    assert freqs.ftf_order == pytest.approx(0.398, abs=0.002)
    # A ball defect strikes both races per revolution, so 2xBSF is what shows.
    assert freqs.bsf_2x_order == pytest.approx(2 * freqs.bsf_order, abs=1e-9)


def test_orders_are_speed_invariant():
    """Orders must not move with speed — that is the whole point of using them."""
    slow = fault_frequencies(SKF_6205, 600)
    fast = fault_frequencies(SKF_6205, 3600)

    assert slow.bpfo_order == pytest.approx(fast.bpfo_order, abs=1e-9)
    assert slow.bpfi_order == pytest.approx(fast.bpfi_order, abs=1e-9)


@pytest.mark.parametrize("seed", range(25))
def test_bpfo_plus_bpfi_equals_n_times_shaft_rate(seed):
    """BPFO + BPFI == n*fr for ANY geometry — catches sign and factor errors."""
    rng = random.Random(seed)
    pitch = rng.uniform(20.0, 200.0)
    geom = BearingGeometry(
        n_balls=rng.randint(6, 22),
        ball_dia_mm=pitch * rng.uniform(0.08, 0.30),
        pitch_dia_mm=pitch,
        contact_angle_deg=rng.choice([0.0, 15.0, 30.0, 40.0]),
    )
    rpm = rng.uniform(100.0, 6000.0)
    freqs = fault_frequencies(geom, rpm)

    assert freqs.bpfo_hz + freqs.bpfi_hz == pytest.approx(
        geom.n_balls * freqs.shaft_hz, rel=1e-12
    )


def test_bearing_frequencies_are_non_synchronous():
    """Non-synchronicity is what separates a bearing fault from unbalance."""
    freqs = fault_frequencies(SKF_6205, 1750)

    for order in (freqs.bpfo_order, freqs.bpfi_order, freqs.ftf_order):
        assert abs(order - round(order)) > 0.05


def test_contact_angle_reduces_bpfo():
    """A non-zero contact angle shrinks r, which raises BPFO toward n*fr/2."""
    angled = BearingGeometry(
        n_balls=9, ball_dia_mm=7.94, pitch_dia_mm=39.04, contact_angle_deg=40.0
    )
    assert fault_frequencies(angled, 1750).bpfo_hz > fault_frequencies(SKF_6205, 1750).bpfo_hz


class TestGeometryResolution:
    def test_catalog_hit_is_full_confidence(self):
        geom = resolve_bearing("6205")
        assert geom is not None
        assert geom.source == "catalog"
        assert geom.confidence == 1.0
        assert geom.n_balls == 9
        assert geom.assumptions == ()

    def test_6203_catalog_hit(self):
        geom = resolve_bearing("6203")
        assert geom is not None
        assert geom.n_balls == 8
        assert geom.ball_dia_mm == pytest.approx(6.7462, abs=1e-4)

    @pytest.mark.parametrize(
        "designation",
        ["SKF 6205", "6205-2RS", "6205 ZZ", "skf 6205-2rs1/c3", "FAG 6205", " 6205 "],
    )
    def test_designation_normalization(self, designation):
        assert normalize_designation(designation) == "6205"
        assert resolve_bearing(designation) is not None

    def test_estimated_geometry_is_flagged_and_lower_confidence(self):
        """A bearing not in the catalogue must announce that it was estimated."""
        geom = resolve_bearing("6312")
        assert geom is not None
        assert geom.source == "estimated"
        assert geom.confidence < 1.0
        assert geom.assumptions, "estimated geometry must carry an assumption string"
        assert "estimated" in geom.assumptions[0].lower()

    @pytest.mark.parametrize("designation", ["22312", "NU312", "32210", "", "nonsense"])
    def test_unknown_types_return_none_rather_than_guessing(self, designation):
        """Roller bearings must not get ball-bearing geometry invented for them."""
        assert resolve_bearing(designation) is None

    def test_estimator_reproduces_6205_within_tolerance(self):
        """Calibration check: 25x52 mm boundary dims should land near the real 6205."""
        geom = estimate_geometry(bore_mm=25, outside_dia_mm=52, designation="6205")
        assert geom.n_balls == 9
        assert geom.ball_dia_mm == pytest.approx(7.94, rel=0.05)
        assert geom.pitch_dia_mm == pytest.approx(39.04, rel=0.02)

    def test_explicit_geometry_beats_designation(self):
        """User-supplied numbers come off the datasheet and must win."""
        geom = geometry_from_inputs(
            designation="6205", n_balls=11, ball_dia_mm=8.0, pitch_dia_mm=40.0
        )
        assert geom is not None
        assert geom.n_balls == 11
        assert geom.source == "user"


class TestValidation:
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"n_balls": 0, "ball_dia_mm": 8.0, "pitch_dia_mm": 40.0},
            {"n_balls": 9, "ball_dia_mm": -1.0, "pitch_dia_mm": 40.0},
            {"n_balls": 9, "ball_dia_mm": 50.0, "pitch_dia_mm": 40.0},
            {"n_balls": 9, "ball_dia_mm": 8.0, "pitch_dia_mm": 40.0, "contact_angle_deg": 120.0},
        ],
    )
    def test_impossible_geometry_rejected(self, kwargs):
        with pytest.raises(ValueError):
            BearingGeometry(**kwargs)

    @pytest.mark.parametrize("rpm", [0, -100])
    def test_non_positive_speed_rejected(self, rpm):
        with pytest.raises(ValueError):
            fault_frequencies(SKF_6205, rpm)


def test_record_carries_slip_assumption_and_confidence():
    """The answer must be able to tell the user why an exact match is not expected."""
    record = build_record(fault_frequencies(resolve_bearing("6205"), 1750))

    assert record.tool == "bearing_fault_frequencies"
    assert record.confidence == 1.0
    assert record.outputs["BPFO_hz"] == pytest.approx(104.56, abs=0.05)
    assert any("slip" in a.lower() for a in record.assumptions)
    assert record.formula_source.query_hint


def test_estimated_geometry_lowers_record_confidence():
    record = build_record(fault_frequencies(resolve_bearing("6312"), 1480))
    assert record.confidence < 1.0
    assert len(record.assumptions) >= 2
