"""A health score and an ISO zone that can both be argued with — VIK-055/056.

Two numbers people act on without reading the words around them, so both
have to be right about what they do not know.

**Health (VIK-055)** replaced a three-entry lookup -- normal 100, warning
60, critical 20. The tests that matter are not that a sick machine scores
low; any function does that. They are that a machine nobody can see does
not score 100, that four mild concerns do not outrank one severe fault, and
that criticality does not move the condition.

**ISO (VIK-056)** must return every table that could apply rather than
picking one. The interesting case is the one the ticket does not mention:
when all the applicable tables agree, the missing nameplate data does not
matter and saying so is more useful than a shrug.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.ai.health import CEILINGS, assess, band_for
from app.ai.iso_grade import (
    MIN_DISTINCT_VALUES,
    MIN_GRADEABLE_MM_S,
    WINDOW_NOISE_BANDWIDTH_BINS,
    broadband_velocity_rms,
    foundation_of,
    grade,
    grade_spectrum,
    signal_floor_reason,
)

#: A machine that can be seen properly: baseline in force, spectrum that
#: resolves the diagnostic orders, a capture from half an hour ago.
SEEN_WELL = dict(has_baseline=True, resolution_usable=True,
                 hours_since_capture=0.5, captures_seen=120)


def finding(**overrides):
    base = {"fault_key": "bearing_outer_race", "fault_name": "Outer race",
            "channel": 0, "stage": "severe", "severity": 4,
            "confidence": 0.9, "times_seen": 9, "peak_stage": "severe"}
    base.update(overrides)
    return base


# =====================================================  health  ==========

def test_a_machine_nobody_has_measured_has_no_score():
    """The lookup table's original sin. `None` and 100 are different claims
    and the dashboard has to be able to tell them apart."""
    verdict = assess()
    assert verdict.score is None
    assert verdict.usable is False
    assert verdict.band == "unknown"
    assert "not a healthy one" in verdict.reason


def test_poor_data_lowers_the_ceiling_and_never_the_score():
    """The platform's rule as arithmetic. A machine with no baseline is not
    a machine at 60; it is a machine that cannot be certified at 100."""
    blind = assess(anomaly_scores=[10], has_baseline=False,
                   resolution_usable=False, hours_since_capture=0.5,
                   captures_seen=120)
    good = assess(anomaly_scores=[10], **SEEN_WELL)

    assert blind.ceiling == CEILINGS["blind"]
    assert good.ceiling == CEILINGS["good"]
    assert blind.score is not None and blind.score <= blind.ceiling
    assert blind.score < good.score
    # And it says why, in the same breath as the number.
    assert "data quality" in blind.reason
    assert blind.unknowns


def test_a_clean_well_seen_machine_scores_near_a_hundred():
    verdict = assess(anomaly_scores=[8, 12, 5], **SEEN_WELL)
    assert verdict.score >= 97
    assert verdict.band == "Excellent"


def test_one_severe_fault_outranks_four_mild_concerns():
    """Adding penalties up instead of combining them gets this backwards,
    and the failure is invisible -- both machines just have a number."""
    severe = assess(findings=[finding()], anomaly_scores=[82, 40], **SEEN_WELL)
    scattered = assess(
        anomaly_scores=[55],
        symptoms=[{"key": "a", "name": "Harmonics"},
                  {"key": "b", "name": "Sidebands"}],
        trend_rising=True, active_alarms=[{"severity": "warning"}],
        **SEEN_WELL)

    assert severe.score < scattered.score


def test_engine_confidence_scales_a_named_fault():
    """A severe stage the engine is unsure of is a different claim from a
    severe stage it is certain of."""
    sure = assess(findings=[finding(confidence=0.9)], **SEEN_WELL)
    unsure = assess(findings=[finding(confidence=0.25)], **SEEN_WELL)
    assert unsure.score > sure.score


def test_the_score_cannot_leave_the_scale():
    """Everything wrong at once. A sum would go negative and be clamped,
    which silently throws away the difference between bad and much worse."""
    verdict = assess(
        findings=[finding(stage="critical", severity=5, confidence=1.0)],
        anomaly_scores=[100, 99, 98],
        active_alarms=[{"severity": "critical"}, {"severity": "warning"}],
        trend_rising=True,
        symptoms=[{"key": "s", "name": "Impacting"}], **SEEN_WELL)

    assert 0.0 <= verdict.score <= 100.0
    assert verdict.band == "Critical"


def test_criticality_moves_priority_and_leaves_condition_alone():
    """A spare pump and a boiler feed pump in identical condition are in
    identical condition. Letting criticality move the score makes the
    number answer two questions and check against neither."""
    args = dict(findings=[finding(severity=3, stage="developing")],
                anomaly_scores=[70], **SEEN_WELL)
    high = assess(criticality="critical", **args)
    low = assess(criticality="low", **args)

    assert high.score == low.score
    assert high.priority > low.priority


def test_every_contribution_carries_its_reason_and_the_points_add_up():
    """A score nobody can take apart is the lookup table with more decimal
    places."""
    verdict = assess(
        findings=[finding(severity=3, stage="developing", confidence=0.7)],
        anomaly_scores=[70], trend_rising=True,
        active_alarms=[{"severity": "warning"}],
        symptoms=[{"key": "s", "name": "Impacting"}], **SEEN_WELL)

    assert verdict.contributions
    for item in verdict.contributions:
        assert item.reason, f"{item.key} moved the score without saying why"
        assert item.points >= 0

    attributed = sum(c.points for c in verdict.contributions)
    assert attributed == pytest.approx(verdict.ceiling - verdict.score,
                                       abs=0.15)


def test_contributions_are_ordered_by_size_not_by_code_order():
    """Otherwise moving two blocks in the module changes every number on
    the screen without changing a single input."""
    verdict = assess(
        findings=[finding()], anomaly_scores=[70], trend_rising=True,
        active_alarms=[{"severity": "warning"}], **SEEN_WELL)
    points = [c.points for c in verdict.contributions]
    assert points == sorted(points, reverse=True)


def test_a_recovered_machine_reads_healthy_but_keeps_its_history():
    """It has to be able to come back. A machine held at 70 forever because
    it was once ill is a machine whose score stops being read."""
    verdict = assess(
        findings=[finding(severity=0, stage="normal", peak_stage="severe")],
        anomaly_scores=[15], **SEEN_WELL)

    assert verdict.band in ("Excellent", "Good")
    assert any(c.key == "history" for c in verdict.contributions)


def test_an_unmeasurable_trend_is_recorded_as_unknown_not_as_steady():
    """On this gateway the steadiness check never runs -- the record is too
    short. That must not read as "not getting worse"."""
    verdict = assess(anomaly_scores=[20], trend_rising=None, **SEEN_WELL)
    assert any("getting worse" in u for u in verdict.unknowns)
    assert all(c.key != "trend" for c in verdict.contributions)


def test_the_bands_are_the_ones_requirement_12_1_specifies():
    """Verbatim, boundaries and words.

    These were originally invented -- five bands at different cut-offs,
    "healthy" and "acceptable" for "Excellent" and "Good" -- on the
    reasoning that a health band and a fault stage should not share
    vocabulary. The reasoning was sound and the decision was still wrong:
    the document sets the boundaries and the words, somebody will check the
    screen against it, and a band reading "degraded" where the
    specification says "Watch" is a defect however well argued.
    """
    assert band_for(None) == "unknown"
    for score, expected in ((100, "Excellent"), (90, "Excellent"),
                            (89, "Good"), (75, "Good"),
                            (74, "Watch"), (60, "Watch"),
                            (59, "Poor"), (40, "Poor"),
                            (39, "High risk"), (20, "High risk"),
                            (19, "Critical"), (0, "Critical")):
        assert band_for(score) == expected, score


def test_trend_acceleration_is_its_own_input():
    """Requirement 12.1 lists it separately from the trend, and is right
    to: something getting worse steadily and something getting worse faster
    and faster are different amounts of time to act in."""
    steady = assess(anomaly_scores=[60], trend_rising=True,
                    trend_accelerating=False, **SEEN_WELL)
    speeding = assess(anomaly_scores=[60], trend_rising=True,
                      trend_accelerating=True, **SEEN_WELL)

    assert speeding.score < steady.score
    assert any(c.key == "acceleration" for c in speeding.contributions)


def test_unknown_acceleration_is_not_reported_as_steady():
    verdict = assess(anomaly_scores=[60], trend_rising=True,
                     trend_accelerating=None, **SEEN_WELL)
    assert all(c.key != "acceleration" for c in verdict.contributions)
    assert any("speeding up" in u for u in verdict.unknowns)


# ========================================================  ISO  ==========

def test_when_every_applicable_table_agrees_the_missing_data_stops_mattering():
    """The useful half of the ticket. At 1.2 mm/s nobody needs to find the
    nameplate, and refusing to answer would be pedantry."""
    verdict = grade(velocity_rms_mm_s=1.2)
    assert verdict.usable is True
    assert verdict.zone == "A"
    assert len(verdict.candidates) > 1
    assert verdict.determined is False
    assert "do not change the answer" in verdict.reason


def test_when_the_tables_disagree_no_single_zone_is_reported():
    """The ticket's hard requirement. 4.5 mm/s is Zone B on one table and
    Zone C on another, and picking one produces a guess that looks exactly
    like a measurement."""
    verdict = grade(velocity_rms_mm_s=4.5)

    assert verdict.zone is None
    assert verdict.usable is False
    assert verdict.zone_range == ["B", "C"]
    assert len(verdict.candidates) > 1
    # Every table it could be is returned, not just the fact of ambiguity.
    assert {c["machine_group"] for c in verdict.candidates} == {1, 2, 3, 4}
    assert verdict.missing, "it has to say what would settle it"


def test_the_worst_case_is_still_available_when_the_tables_disagree():
    """A conservative reader needs the ceiling of the uncertainty even when
    no single answer exists."""
    assert grade(velocity_rms_mm_s=4.5).worst_zone == "C"


def test_a_complete_machine_record_gives_one_table_and_one_zone():
    verdict = grade(velocity_rms_mm_s=4.5, machine_type="Centrifugal Pump",
                    power_kw=55.0, foundation="rigid concrete plinth")
    assert verdict.determined is True
    assert len(verdict.candidates) == 1
    assert verdict.zone == "B"
    assert not verdict.zone_range


def test_no_velocity_is_not_zone_a():
    verdict = grade(velocity_rms_mm_s=None)
    assert verdict.zone is None
    assert verdict.usable is False
    assert "not the same as Zone A" in verdict.reason


def test_an_unclassifiable_foundation_grades_both_rather_than_guessing():
    """The two foundation tables differ by about 60%, so a default here is
    a silent coin toss."""
    verdict = grade(velocity_rms_mm_s=4.5, machine_type="pump", power_kw=55.0,
                    foundation="steel")
    assert {c["foundation"] for c in verdict.candidates} == {"rigid",
                                                             "flexible"}
    assert any("rigid or flexible" in m for m in verdict.missing)


def test_foundation_words_map_only_when_they_are_unambiguous():
    assert foundation_of("rigid concrete") == "rigid"
    assert foundation_of("spring isolated skid") == "flexible"
    assert foundation_of("steel") is None, "could be a baseplate or a frame"
    assert foundation_of(None) is None


def test_the_integrated_velocity_matches_the_hand_calculation():
    """The window correction is easy to leave out and costs 22% -- enough
    on its own to move a machine from Zone B into Zone C.

    A 1 g peak tone at 24.67 Hz is 9806.65 / (2*pi*f) / sqrt(2) mm/s RMS.
    """
    fs, seconds, shaft = 25_600.0, 4.0, 24.67
    n = int(fs * seconds)
    signal = np.sin(2 * np.pi * shaft * np.arange(n) / fs)
    window = np.hanning(n)
    mags = np.abs(np.fft.rfft(signal * window)) * 2 / np.sum(window)
    freqs = np.fft.rfftfreq(n, 1 / fs)

    got = broadband_velocity_rms(freqs, mags)
    expected = 9806.65 / (2 * np.pi * shaft) / np.sqrt(2)

    assert got["velocity_rms_mm_s"] == pytest.approx(expected, rel=0.02)


def test_dropping_the_window_correction_would_be_caught():
    """A mutation guard. Without it this test file would pass whether or
    not the correction is applied, because every other assertion here is
    about zones rather than the number under them."""
    fs, seconds, shaft = 25_600.0, 4.0, 24.67
    n = int(fs * seconds)
    signal = np.sin(2 * np.pi * shaft * np.arange(n) / fs)
    window = np.hanning(n)
    mags = np.abs(np.fft.rfft(signal * window)) * 2 / np.sum(window)
    freqs = np.fft.rfftfreq(n, 1 / fs)

    corrected = broadband_velocity_rms(freqs, mags)["velocity_rms_mm_s"]
    uncorrected = broadband_velocity_rms(
        freqs, mags, window_noise_bandwidth_bins=1.0)["velocity_rms_mm_s"]

    assert uncorrected > corrected
    assert uncorrected / corrected == pytest.approx(
        np.sqrt(WINDOW_NOISE_BANDWIDTH_BINS), rel=0.01)


def test_a_record_too_short_to_reach_the_band_refuses_to_report_one():
    """A velocity RMS over 40-1000 Hz is not the quantity the standard's
    limits refer to, and nothing downstream could tell the difference."""
    freqs = np.fft.rfftfreq(64, 1 / 1000.0)      # 15.6 Hz per bin
    mags = np.ones(freqs.size) * 1e-4

    got = broadband_velocity_rms(freqs, mags)
    assert got["velocity_rms_mm_s"] is None
    assert got["missing"]


def test_grade_spectrum_carries_the_velocity_gaps_into_the_verdict():
    freqs = np.fft.rfftfreq(64, 1 / 1000.0)
    mags = np.ones(freqs.size) * 1e-4
    verdict = grade_spectrum(freqs, mags, machine_type="pump", power_kw=55.0,
                             foundation="rigid")
    assert verdict.usable is False
    assert verdict.missing


# ----------------------------------------------- the signal floor --------

def test_a_capture_made_of_quantisation_noise_does_not_grade_zone_a():
    """Found by running this against the real gateway, not by reasoning.

    That capture integrated to 0.027 mm/s and came back **Zone A, typical of
    newly commissioned machines** -- because its eight channels span about
    thirteen distinct converter values and the spectrum is mostly rounding.
    A running pump reads one to three mm/s. Somebody would have read the
    platform's own output as a clean bill of health on a machine it could
    not see at all.
    """
    verdict = grade(velocity_rms_mm_s=0.027, machine_type="pump",
                    power_kw=55.0, foundation="rigid", distinct_values=13)

    assert verdict.zone is None
    assert verdict.usable is False
    assert "converter rounding" in verdict.reason
    assert verdict.missing


def test_a_stopped_machine_does_not_grade_zone_a_either():
    """A stopped machine and an as-new machine both read near zero, and the
    standard's best zone is what that comes out as when nobody checks."""
    verdict = grade(velocity_rms_mm_s=0.02, machine_type="pump",
                    power_kw=55.0, foundation="rigid", distinct_values=4096)

    assert verdict.zone is None
    assert "stopped" in verdict.reason


def test_a_real_reading_from_a_real_signal_still_grades():
    """The guard must not swallow the ordinary case."""
    verdict = grade(velocity_rms_mm_s=1.2, machine_type="pump",
                    power_kw=55.0, foundation="rigid", distinct_values=4096)
    assert verdict.zone == "A"
    assert verdict.usable is True


def test_the_floor_check_names_which_limit_was_hit():
    assert signal_floor_reason(5.0, MIN_DISTINCT_VALUES + 1) is None
    assert "distinct sample values" in signal_floor_reason(5.0, 13)
    assert "stopped" in signal_floor_reason(MIN_GRADEABLE_MM_S / 2, 4096)


def test_grade_spectrum_counts_distinct_values_from_the_waveform():
    """The count has to come from the samples; a spectrum cannot show how
    coarsely the converter rounded."""
    fs, seconds, shaft = 25_600.0, 1.0, 24.67
    n = int(fs * seconds)
    clean = np.sin(2 * np.pi * shaft * np.arange(n) / fs)
    coarse = np.round(clean * 6) / 6        # a handful of distinct levels

    window = np.hanning(n)

    def spectrum(signal):
        mags = np.abs(np.fft.rfft(signal * window)) * 2 / np.sum(window)
        return np.fft.rfftfreq(n, 1 / fs), mags

    freqs, mags = spectrum(coarse)
    blocked = grade_spectrum(freqs, mags, samples=coarse, machine_type="pump",
                             power_kw=55.0, foundation="rigid")
    assert blocked.usable is False
    assert "distinct sample values" in blocked.reason

    freqs, mags = spectrum(clean)
    graded = grade_spectrum(freqs, mags, samples=clean, machine_type="pump",
                            power_kw=55.0, foundation="rigid")
    assert graded.zone is not None
