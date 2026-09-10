"""ISO 10816-3 severity zone lookup.

Every boundary is tested from both sides. A maintenance decision hangs on which
side of 2.80 mm/s a reading falls, so the convention must be pinned, not
inferred.
"""

from __future__ import annotations

import pytest

from app.domain.iso10816 import (
    build_record,
    displacement_zone,
    infer_machine_group,
    severity_zone,
    summarize,
)

# group, foundation, (A/B, B/C, C/D)
BOUNDARY_MATRIX = [
    (1, "rigid", (2.3, 4.5, 7.1)),
    (1, "flexible", (3.5, 7.1, 11.0)),
    (2, "rigid", (1.4, 2.8, 4.5)),
    (2, "flexible", (2.3, 4.5, 7.1)),
    (3, "rigid", (2.3, 4.5, 7.1)),
    (3, "flexible", (3.5, 7.1, 11.0)),
    (4, "rigid", (1.4, 2.8, 4.5)),
    (4, "flexible", (2.3, 4.5, 7.1)),
]


@pytest.mark.parametrize("group,foundation,expected", BOUNDARY_MATRIX)
def test_boundary_values_match_the_standard(group, foundation, expected):
    result = severity_zone(1.0, group, foundation)
    ab, bc, cd = expected
    assert (result.boundaries["A/B"], result.boundaries["B/C"], result.boundaries["C/D"]) == (ab, bc, cd)


@pytest.mark.parametrize("group,foundation,expected", BOUNDARY_MATRIX)
def test_zone_assignment_on_both_sides_of_every_boundary(group, foundation, expected):
    """A value exactly ON a boundary belongs to the LOWER zone."""
    ab, bc, cd = expected
    eps = 0.01

    assert severity_zone(ab - eps, group, foundation).zone == "A"
    assert severity_zone(ab, group, foundation).zone == "A"
    assert severity_zone(ab + eps, group, foundation).zone == "B"

    assert severity_zone(bc, group, foundation).zone == "B"
    assert severity_zone(bc + eps, group, foundation).zone == "C"

    assert severity_zone(cd, group, foundation).zone == "C"
    assert severity_zone(cd + eps, group, foundation).zone == "D"


def test_group2_rigid_documented_case():
    """The canonical example: 2.80 -> B, 2.81 -> C."""
    assert severity_zone(2.79, 2, "rigid").zone == "B"
    assert severity_zone(2.80, 2, "rigid").zone == "B"
    assert severity_zone(2.81, 2, "rigid").zone == "C"


def test_55kw_pump_at_4_9_is_zone_c():
    """The worked example the bot is expected to handle end to end."""
    result = severity_zone(4.9, 3, "rigid")

    assert result.zone == "C"
    assert result.urgency == "scheduled"
    assert "long-term" in result.zone_meaning.lower()
    assert result.next_zone == "D"
    assert result.margin_to_next_mm_s == pytest.approx(2.2, abs=0.01)


def test_zone_d_has_no_next_zone():
    result = severity_zone(20.0, 2, "rigid")
    assert result.zone == "D"
    assert result.next_zone is None
    assert result.margin_to_next_mm_s is None
    assert result.urgency == "immediate"


def test_margin_flags_a_reading_close_to_the_next_zone():
    """"Zone B" and "Zone B, 0.02 from C" are different operational messages."""
    result = severity_zone(2.78, 2, "rigid")
    assert result.zone == "B"
    assert result.margin_to_next_mm_s == pytest.approx(0.02, abs=1e-6)


class TestValidation:
    @pytest.mark.parametrize("group", [0, 5, 99, -1])
    def test_invalid_group_rejected(self, group):
        with pytest.raises(ValueError, match="machine_group"):
            severity_zone(3.0, group, "rigid")

    @pytest.mark.parametrize("foundation", ["soft", "", "RIGID_ISH", None])
    def test_invalid_foundation_rejected(self, foundation):
        with pytest.raises(ValueError, match="foundation"):
            severity_zone(3.0, 2, foundation)

    def test_negative_velocity_rejected(self):
        with pytest.raises(ValueError):
            severity_zone(-1.0, 2, "rigid")

    def test_unknown_standard_rejected(self):
        with pytest.raises(ValueError, match="standard"):
            severity_zone(3.0, 2, "rigid", standard="10816-7")

    def test_foundation_is_case_insensitive(self):
        assert severity_zone(3.0, 2, "RIGID").zone == severity_zone(3.0, 2, "rigid").zone


def test_20816_supersedes_10816_with_same_limits():
    """Analysts will ask for 20816-3; the limits are the same, the citation is not."""
    old = severity_zone(3.0, 2, "rigid", standard="10816-3")
    new = severity_zone(3.0, 2, "rigid", standard="20816-3")

    assert old.zone == new.zone
    assert old.boundaries == new.boundaries
    assert "10816" in old.standard
    assert "20816" in new.standard


class TestGroupInference:
    @pytest.mark.parametrize(
        "power,kind,integrated,expected",
        [
            (55, "pump", False, 3),
            (55, "pump", True, 4),
            (500, "centrifugal pump", False, 3),
            (55, "motor", False, 2),
            (500, "fan", False, 1),
            (15000, "turbine", False, 1),
            (5, "motor", False, None),
            (None, None, False, None),
        ],
    )
    def test_group_from_nameplate(self, power, kind, integrated, expected):
        assert infer_machine_group(power, kind, integrated_driver=integrated) == expected

    def test_falls_back_to_shaft_height_for_electrical_machines(self):
        assert infer_machine_group(None, "motor", shaft_height_mm=400) == 1
        assert infer_machine_group(None, "motor", shaft_height_mm=200) == 2
        assert infer_machine_group(None, "motor", shaft_height_mm=100) is None


def test_displacement_zone_refuses_rather_than_guessing():
    """The micrometre columns are not transcribed; guessing them is the failure
    this module exists to prevent."""
    with pytest.raises(NotImplementedError, match="not transcribed"):
        displacement_zone(50.0, 2, "rigid")


def test_record_states_measurement_conditions():
    """A reading over a different band is not comparable to these limits."""
    record = build_record(severity_zone(4.9, 3, "rigid"))

    assert record.confidence == 1.0
    assert record.outputs["zone"] == "C"
    assert any("10-1000" in a for a in record.assumptions)
    assert any("lower zone" in a.lower() for a in record.assumptions)


def test_summary_mentions_zone_action_and_boundaries():
    text = summarize(severity_zone(4.9, 3, "rigid"))
    assert "ZONE C" in text
    assert "4.5" in text
