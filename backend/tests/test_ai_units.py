"""Amplitude conversion between acceleration, velocity and displacement."""

from __future__ import annotations

import math

import pytest

from app.ai.units import G_TO_MM_S2, build_record, convert_amplitude


def test_1g_rms_at_100hz_is_15_61_mm_s():
    """The textbook worked example: v = a / omega."""
    result = convert_amplitude(1.0, "g", "mm/s", frequency_hz=100)

    expected = G_TO_MM_S2 / (2 * math.pi * 100)
    assert result.value == pytest.approx(expected, rel=1e-9)
    assert result.value == pytest.approx(15.61, abs=0.01)


def test_1g_peak_to_velocity_rms():
    """Measure conversion and quantity conversion compose correctly."""
    result = convert_amplitude(
        1.0, "g", "mm/s", frequency_hz=100, from_measure="peak", to_measure="rms"
    )
    assert result.value == pytest.approx(11.04, abs=0.01)


@pytest.mark.parametrize("frequency", [1.0, 25.0, 60.0, 100.0, 1000.0])
def test_round_trip_is_identity(frequency):
    forward = convert_amplitude(2.5, "g", "mm/s", frequency_hz=frequency)
    back = convert_amplitude(forward.value, "mm/s", "g", frequency_hz=frequency)
    assert back.value == pytest.approx(2.5, rel=1e-9)


@pytest.mark.parametrize(
    "from_unit,to_unit", [("g", "um"), ("mm/s", "um"), ("um", "g"), ("in/s", "mm/s")]
)
def test_round_trip_across_all_quantity_pairs(from_unit, to_unit):
    forward = convert_amplitude(3.0, from_unit, to_unit, frequency_hz=50)
    back = convert_amplitude(forward.value, to_unit, from_unit, frequency_hz=50)
    assert back.value == pytest.approx(3.0, rel=1e-9)


class TestMeasureConversion:
    def test_rms_to_peak_is_root_two(self):
        result = convert_amplitude(1.0, "mm/s", "mm/s", from_measure="rms", to_measure="peak")
        assert result.value == pytest.approx(math.sqrt(2), rel=1e-12)

    def test_peak_to_peak_is_double_peak(self):
        result = convert_amplitude(1.0, "mm/s", "mm/s", from_measure="peak", to_measure="pk-pk")
        assert result.value == pytest.approx(2.0, rel=1e-12)

    def test_rms_to_pk_pk(self):
        result = convert_amplitude(1.0, "mm/s", "mm/s", from_measure="rms", to_measure="pk-pk")
        assert result.value == pytest.approx(2 * math.sqrt(2), rel=1e-12)

    @pytest.mark.parametrize("alias,canonical", [("pkpk", "pk-pk"), ("p-p", "pk-pk"), ("pk", "peak")])
    def test_measure_aliases(self, alias, canonical):
        via_alias = convert_amplitude(1.0, "mm/s", "mm/s", from_measure="rms", to_measure=alias)
        via_name = convert_amplitude(1.0, "mm/s", "mm/s", from_measure="rms", to_measure=canonical)
        assert via_alias.value == pytest.approx(via_name.value)


class TestUnitConversion:
    def test_mils_to_microns(self):
        result = convert_amplitude(2.0, "mil", "um", from_measure="pk-pk", to_measure="pk-pk")
        assert result.value == pytest.approx(50.8, rel=1e-9)

    def test_g_to_ms2(self):
        result = convert_amplitude(1.0, "g", "m/s2")
        assert result.value == pytest.approx(9.80665, rel=1e-9)

    def test_in_per_s_to_mm_per_s(self):
        assert convert_amplitude(1.0, "in/s", "mm/s").value == pytest.approx(25.4, rel=1e-9)

    @pytest.mark.parametrize("alias", ["G", "g "])
    def test_unit_aliases(self, alias):
        assert convert_amplitude(1.0, alias, "m/s2").value == pytest.approx(9.80665, rel=1e-6)


def test_same_quantity_conversion_needs_no_frequency():
    """g -> m/s2 is a scale factor; demanding a frequency would be wrong."""
    result = convert_amplitude(1.0, "g", "m/s2")
    assert result.quantity_changed is False
    assert result.frequency_hz is None


@pytest.mark.parametrize("frequency", [None, 0, -5])
def test_cross_quantity_conversion_requires_positive_frequency(frequency):
    with pytest.raises(ValueError, match="frequency_hz"):
        convert_amplitude(1.0, "g", "mm/s", frequency_hz=frequency)


def test_unknown_unit_and_measure_rejected():
    with pytest.raises(ValueError, match="Unknown unit"):
        convert_amplitude(1.0, "furlongs", "mm/s")
    with pytest.raises(ValueError, match="Unknown measure"):
        convert_amplitude(1.0, "mm/s", "mm/s", from_measure="average")


def test_cross_quantity_result_warns_about_single_frequency_assumption():
    """Silently applying this to a broadband overall reading is the trap."""
    result = convert_amplitude(1.0, "g", "mm/s", frequency_hz=100)

    assert result.warnings
    assert any("single sinusoid" in w for w in result.warnings)
    assert build_record(result, 1.0).confidence < 1.0


def test_same_quantity_result_is_exact_and_unwarned():
    result = convert_amplitude(1.0, "g", "m/s2")
    assert result.warnings == []
    assert build_record(result, 1.0).confidence == 1.0


def test_measure_change_warns_about_crest_factor():
    result = convert_amplitude(1.0, "mm/s", "mm/s", from_measure="rms", to_measure="peak")
    assert any("crest factor" in w for w in result.warnings)
