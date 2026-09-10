"""Fault-signature ranking.

These are the cases an analyst would recognise instantly from a spectrum, so
they are the right thing to hold the rule table to.
"""

from __future__ import annotations

import pytest

from app.domain.bearing import fault_frequencies, resolve_bearing
from app.domain.signatures import (
    MachineContext,
    SpectralPeak,
    build_record,
    cross_check_bearing_peaks,
    match_faults,
)

SHAFT_RPM = 1750.0
SHAFT_HZ = SHAFT_RPM / 60.0


def peaks(orders: dict[float, float], direction: str = "", source: str = "waveform", confidence: float = 1.0):
    return [
        SpectralPeak(
            frequency_hz=order * SHAFT_HZ,
            amplitude=amplitude,
            order=order,
            direction=direction,
            source=source,
            confidence=confidence,
        )
        for order, amplitude in orders.items()
    ]


def bearing_context(designation: str = "6205", **kwargs) -> MachineContext:
    freqs = fault_frequencies(resolve_bearing(designation), SHAFT_RPM)
    return MachineContext(
        shaft_rpm=SHAFT_RPM,
        bearing_orders={
            "bpfo": freqs.bpfo_order,
            "bpfi": freqs.bpfi_order,
            "bsf": freqs.bsf_order,
            "bsf2x": freqs.bsf_2x_order,
            "ftf": freqs.ftf_order,
        },
        **kwargs,
    )


def top_key(hypotheses) -> str:
    assert hypotheses, "expected at least one hypothesis"
    return hypotheses[0].fault_key


class TestSynchronousFaults:
    def test_dominant_1x_is_unbalance(self):
        result = match_faults(peaks({1.0: 0.9, 2.0: 0.2}), MachineContext(shaft_rpm=SHAFT_RPM))
        assert top_key(result) == "unbalance"

    def test_dominant_2x_is_parallel_misalignment(self):
        result = match_faults(peaks({1.0: 0.4, 2.0: 0.9, 3.0: 0.2}), MachineContext(shaft_rpm=SHAFT_RPM))
        assert top_key(result) == "misalignment_parallel"

    def test_half_order_series_is_mechanical_looseness(self):
        """0.5x subharmonics are what separate looseness from a soft foot."""
        result = match_faults(
            peaks({0.5: 0.6, 1.0: 0.8, 1.5: 0.5, 2.0: 0.6, 2.5: 0.4, 3.0: 0.5, 4.0: 0.3}),
            MachineContext(shaft_rpm=SHAFT_RPM),
        )
        assert top_key(result) == "mechanical_looseness"

    def test_small_2x_does_not_defeat_unbalance(self):
        """A weak 2x alongside a dominant 1x is normal, not evidence against."""
        result = match_faults(peaks({1.0: 0.9, 2.0: 0.15}), MachineContext(shaft_rpm=SHAFT_RPM))
        unbalance = next(h for h in result if h.fault_key == "unbalance")
        assert unbalance.score > 0.85

    def test_unbalance_requires_1x_to_actually_dominate(self):
        """1x present but small is not unbalance."""
        result = match_faults(peaks({1.0: 0.1, 2.0: 0.9}), MachineContext(shaft_rpm=SHAFT_RPM))
        assert "unbalance" not in [h.fault_key for h in result]


class TestBearingFaults:
    def test_bpfo_peak_is_outer_race_defect(self):
        ctx = bearing_context()
        result = match_faults(peaks({1.0: 0.2, 3.585: 0.95, 7.17: 0.4}), ctx)
        assert top_key(result) == "bearing_outer_race"

    def test_bpfi_peak_is_inner_race_defect(self):
        ctx = bearing_context()
        result = match_faults(peaks({1.0: 0.2, 5.415: 0.95}), ctx)
        assert top_key(result) == "bearing_inner_race"

    def test_bearing_rules_skipped_without_bearing_geometry(self):
        """No geometry means the rule is untestable, not that it failed."""
        result = match_faults(peaks({3.585: 0.95}), MachineContext(shaft_rpm=SHAFT_RPM))
        assert not any(h.fault_key.startswith("bearing_") for h in result)

    def test_slip_tolerance_accepts_a_slightly_low_peak(self):
        """Real bearings slip ~1%, so measured BPFO sits just below kinematic."""
        ctx = bearing_context()
        result = match_faults(peaks({1.0: 0.2, 3.55: 0.95}), ctx)
        assert top_key(result) == "bearing_outer_race"

    def test_peak_far_from_bpfo_is_not_matched(self):
        ctx = bearing_context()
        result = match_faults(peaks({1.0: 0.2, 3.0: 0.95}), ctx)
        assert not any(h.fault_key == "bearing_outer_race" for h in result)


class TestCrossCheck:
    def test_non_synchronous_peak_matched_to_computed_bpfo(self):
        """The highest-value behaviour: an unexplained peak becomes a named one."""
        ctx = bearing_context()
        peak_list = peaks({1.0: 0.2, 3.585: 0.95})
        notes = cross_check_bearing_peaks(peak_list, ctx.bearing_orders)

        assert len(notes) == 1
        assert "BPFO" in notes[0]
        assert peak_list[1].label == "BPFO"

    def test_synchronous_peaks_are_never_cross_checked(self):
        ctx = bearing_context()
        assert cross_check_bearing_peaks(peaks({1.0: 0.9, 2.0: 0.5}), ctx.bearing_orders) == []


class TestContextGating:
    def test_gear_mesh_absent_without_a_gearbox(self):
        result = match_faults(peaks({1.0: 0.9}), MachineContext(shaft_rpm=SHAFT_RPM), top_n=10)
        assert "gear_mesh" not in [h.fault_key for h in result]

    def test_gear_mesh_found_when_teeth_known(self):
        ctx = MachineContext(shaft_rpm=SHAFT_RPM, gear_mesh_orders=[23.0])
        result = match_faults(peaks({1.0: 0.2, 23.0: 0.95}), ctx)
        assert top_key(result) == "gear_mesh"

    def test_vane_pass_found_when_vane_count_known(self):
        ctx = MachineContext(shaft_rpm=SHAFT_RPM, vane_pass_order=7.0)
        result = match_faults(peaks({1.0: 0.2, 7.0: 0.95}), ctx)
        assert top_key(result) == "blade_vane_pass"

    def test_electrical_uses_supply_frequency_not_shaft_order(self):
        """2xLF is pinned to the supply, so its order depends on running speed."""
        ctx = MachineContext(shaft_rpm=1478.0, line_freq_hz=50.0)
        order_2lf = 100.0 / (1478.0 / 60.0)
        result = match_faults(
            [SpectralPeak(frequency_hz=100.0, amplitude=0.95, order=order_2lf),
             SpectralPeak(frequency_hz=24.63, amplitude=0.2, order=1.0)],
            ctx,
        )
        assert top_key(result) == "electrical"

    def test_oil_whirl_excluded_for_rolling_element_bearings(self):
        ctx = MachineContext(shaft_rpm=SHAFT_RPM, has_journal_bearings=False)
        result = match_faults(peaks({0.43: 0.95, 1.0: 0.3}), ctx, top_n=10)
        assert "oil_whirl" not in [h.fault_key for h in result]

    def test_oil_whirl_included_for_journal_bearings(self):
        ctx = MachineContext(shaft_rpm=SHAFT_RPM, has_journal_bearings=True, has_rolling_bearings=False)
        result = match_faults(peaks({0.43: 0.95, 1.0: 0.3}), ctx)
        assert top_key(result) == "oil_whirl"


class TestDirectionality:
    def test_axial_measurement_supports_angular_misalignment(self):
        axial = match_faults(peaks({1.0: 0.85, 2.0: 0.9, 3.0: 0.3}, direction="A"), MachineContext(shaft_rpm=SHAFT_RPM))
        radial = match_faults(peaks({1.0: 0.85, 2.0: 0.9, 3.0: 0.3}, direction="H"), MachineContext(shaft_rpm=SHAFT_RPM))

        axial_score = next(h.score for h in axial if h.fault_key == "misalignment_angular")
        radial_score = next(h.score for h in radial if h.fault_key == "misalignment_angular")
        assert axial_score > radial_score

    def test_missing_axial_data_is_reported_as_a_gap(self):
        result = match_faults(peaks({1.0: 0.85, 2.0: 0.9}), MachineContext(shaft_rpm=SHAFT_RPM))
        angular = next(h for h in result if h.fault_key == "misalignment_angular")
        assert any("axial" in e.statement.lower() for e in angular.contradicting_evidence)


class TestProvenance:
    def test_chart_read_peaks_cap_hypothesis_confidence(self):
        """A diagnosis from a screenshot must not read as firmly as one from data."""
        from_waveform = match_faults(peaks({1.0: 0.9, 2.0: 0.2}), MachineContext(shaft_rpm=SHAFT_RPM))
        from_chart = match_faults(
            peaks({1.0: 0.9, 2.0: 0.2}, source="chart_vlm", confidence=0.7),
            MachineContext(shaft_rpm=SHAFT_RPM),
        )

        assert from_waveform[0].fault_key == from_chart[0].fault_key
        assert from_waveform[0].score == pytest.approx(from_chart[0].score)
        assert from_chart[0].confidence < from_waveform[0].confidence

    def test_record_confidence_follows_the_weakest_peak(self):
        peak_list = peaks({1.0: 0.9}, source="chart_vlm", confidence=0.7)
        record = build_record(match_faults(peak_list, MachineContext(shaft_rpm=SHAFT_RPM)), peak_list, MachineContext(shaft_rpm=SHAFT_RPM), [])
        assert record.confidence == pytest.approx(0.7)


class TestPeakBasics:
    @pytest.mark.parametrize("order,expected", [(1.0, True), (2.0, True), (1.99, True), (3.585, False), (0.43, False)])
    def test_synchronicity_detection(self, order, expected):
        assert SpectralPeak(frequency_hz=order * SHAFT_HZ, amplitude=1.0, order=order).is_synchronous is expected

    def test_empty_peak_list_yields_no_hypotheses(self):
        assert match_faults([], MachineContext(shaft_rpm=SHAFT_RPM)) == []

    def test_peaks_without_orders_are_ignored(self):
        assert match_faults([SpectralPeak(frequency_hz=29.17, amplitude=1.0)], MachineContext(shaft_rpm=SHAFT_RPM)) == []
