"""Naming the fault — VIK-050, 052, 053, 054.

Phase 3 is the demo, and the thing being demonstrated is not that the
platform can produce a diagnosis. It is that the diagnosis can be argued
with: every finding carries the orders and amplitudes it fired on, and every
absence of a finding says whether the instrument could have seen one.

The tests here fall into three groups.

**The engine really does name faults.** Synthetic signatures with known
answers -- unbalance is 1x dominant, parallel misalignment is 2x dominant,
an outer-race defect is a series at 3.064x on this bearing. If these stop
passing, the wiring has broken, because the rule table itself is tested in
`vibcore`.

**A stage is a claim about time.** VIK-054's one hard rule: a stage rises
only under the persistence conditions, never on one reading. The tests walk
a finding capture by capture rather than asserting on a single call,
because the rule is about the sequence.

**"Cannot tell" is not "nothing found".** The two read identically on a
screen and mean opposite things. On this gateway a 0.278 s record cannot
separate the outer-race frequency from the third shaft harmonic, so the
platform must say that rather than report a healthy machine.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.ai.fault_resolution import MIN_BIN_SEPARATION, assess_resolution
from app.ai.severity import STAGES, ceiling_for, grade
from app.services.fault_context import context_completeness, peaks_from_spectrum
from vibcore.signatures import MachineContext, match_faults

SHAFT_HZ = 24.67
FS = 25_600.0
SECONDS = 4.0

#: The pump's real bearing, from the catalogue.
BEARING = {"ftf": 0.383, "bsf": 2.02, "bpfo": 3.064, "bpfi": 4.936}


def spectrum(signal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    window = np.hanning(signal.size)
    mags = np.abs(np.fft.rfft(signal * window)) * 2 / np.sum(window)
    return np.fft.rfftfreq(signal.size, 1 / FS), mags


def timebase() -> np.ndarray:
    return np.arange(int(FS * SECONDS)) / FS


def context() -> MachineContext:
    return MachineContext(shaft_rpm=SHAFT_HZ * 60.0,
                          bearing_orders=dict(BEARING), vane_pass_order=5.0)


def diagnose(signal: np.ndarray, direction: str = "horizontal"):
    freqs, mags = spectrum(signal)
    peaks = peaks_from_spectrum(freqs, mags, shaft_hz=SHAFT_HZ,
                                direction=direction)
    return match_faults(peaks, context(), top_n=3, min_score=0.2)


# ------------------------------- the engine names real signatures ------

def test_a_one_times_dominant_signal_is_called_unbalance():
    t = timebase()
    signal = 1.0 * np.sin(2 * np.pi * SHAFT_HZ * t) + \
        0.05 * np.sin(2 * np.pi * 2 * SHAFT_HZ * t)
    top = diagnose(signal)[0]
    assert "unbalance" in top.fault_key
    assert top.score > 0.8


def test_a_two_times_dominant_signal_is_called_misalignment():
    t = timebase()
    signal = (0.3 * np.sin(2 * np.pi * SHAFT_HZ * t)
              + 1.0 * np.sin(2 * np.pi * 2 * SHAFT_HZ * t)
              + 0.4 * np.sin(2 * np.pi * 3 * SHAFT_HZ * t))
    assert "misalignment" in diagnose(signal)[0].fault_key


def test_a_series_at_the_outer_race_order_is_called_a_bearing_defect():
    """The one that matters most, and the hardest to get right: 3.064x is
    not a shaft harmonic, and the rule fires on the series rather than on
    any single line."""
    t = timebase()
    signal = 0.2 * np.sin(2 * np.pi * SHAFT_HZ * t) + sum(
        0.8 / k * np.sin(2 * np.pi * 3.064 * k * SHAFT_HZ * t)
        for k in (1, 2, 3))
    top = diagnose(signal)[0]
    assert top.fault_key == "bearing_outer_race"
    assert top.score > 0.8


def test_every_finding_carries_the_evidence_it_fired_on():
    """The whole value of this phase. A finding nobody can interrogate is a
    finding nobody should act on."""
    t = timebase()
    signal = np.sin(2 * np.pi * SHAFT_HZ * t)
    top = diagnose(signal)[0]

    assert top.evidence, "a hypothesis with no evidence is an assertion"
    first = top.evidence[0].as_dict()
    assert first["order"] == pytest.approx(1.0, abs=0.05)
    assert first["frequency_hz"] == pytest.approx(SHAFT_HZ, abs=0.5)
    assert first["amplitude"] is not None
    assert "matched" in first["statement"]


def test_a_machine_detail_nobody_recorded_disables_its_rule():
    """A machine with no tooth count gets no gear-mesh hypothesis -- not a
    gear-mesh hypothesis computed against a guess."""
    completeness = context_completeness(context())
    assert "gear_mesh" in completeness["missing"]
    assert "bearing_orders" in completeness["available"]


def test_no_shaft_speed_means_no_orders_and_no_ranking():
    """Every rule in the table is written in orders. An order computed
    against a guessed speed is wrong by the ratio of the guess."""
    t = timebase()
    freqs, mags = spectrum(np.sin(2 * np.pi * SHAFT_HZ * t))
    peaks = peaks_from_spectrum(freqs, mags, shaft_hz=None)

    assert peaks, "the peaks are still found"
    assert all(p.order is None for p in peaks)
    assert match_faults(peaks, context()) == []


# ------------------------- cannot tell is not nothing found ------------

def test_this_gateways_record_cannot_separate_a_bearing_fault():
    """Measured, not feared. A 0.278 s record resolves 3.60 Hz per bin and
    the outer-race frequency sits 1.58 Hz from the third shaft harmonic."""
    verdict = assess_resolution(
        sample_rate_hz=50_000, sample_count=13_888, shaft_hz=SHAFT_HZ,
        bearing_orders=BEARING, vane_pass_order=5.0)

    assert verdict.usable is False
    assert verdict.bin_hz == pytest.approx(3.6, abs=0.01)
    keys = {item["defect"] for item in verdict.unresolved}
    assert {"bpfo", "bpfi", "bsf"} <= keys
    assert "not evidence the machine is healthy" in verdict.reason


def test_the_verdict_says_how_long_a_record_would_need_to_be():
    """Somebody has to change a setting, and they will want a number."""
    verdict = assess_resolution(
        sample_rate_hz=50_000, sample_count=13_888, shaft_hz=SHAFT_HZ,
        bearing_orders=BEARING, vane_pass_order=5.0)
    assert verdict.needed_seconds is not None
    assert verdict.needed_seconds > 1.0


def test_a_long_enough_record_resolves_the_common_pairs():
    """Two seconds separates the outer race from the third harmonic, which
    is the pair that matters most."""
    verdict = assess_resolution(
        sample_rate_hz=50_000, sample_count=100_000, shaft_hz=SHAFT_HZ,
        bearing_orders=BEARING, vane_pass_order=5.0)
    unresolved = {item["defect"] for item in verdict.unresolved}
    assert "bpfo" not in unresolved
    assert "bpfi" not in unresolved


def test_a_pair_needs_three_bins_not_one():
    """A discrete spectrum spreads one tone over neighbouring bins, so two
    tones one bin apart do not appear as two peaks at all."""
    assert MIN_BIN_SEPARATION >= 3.0


def test_an_unmeasurable_capture_says_so_rather_than_reporting_nothing():
    for kwargs in ({"sample_rate_hz": None, "sample_count": None},
                   {"sample_rate_hz": 50_000, "sample_count": 13_888,
                    "shaft_hz": None}):
        verdict = assess_resolution(shaft_hz=SHAFT_HZ, **kwargs) \
            if "shaft_hz" not in kwargs else assess_resolution(**kwargs)
        assert verdict.usable is False
        assert verdict.reason


# ----------------------------- a stage is a claim about time -----------

def test_a_stage_never_reaches_critical_on_one_reading():
    """VIK-054's hard rule. A severity scale is read as a prediction, and a
    single noisy capture producing "critical" sends people to healthy
    machines until they stop believing the fourth one."""
    first = grade(score=1.0, confidence=1.0, times_seen=1)
    assert first.stage != "critical"
    assert first.severity <= 1


def test_a_stage_climbs_one_step_at_a_time():
    stages, previous = [], None
    for sighting in range(1, 10):
        verdict = grade(score=0.95, confidence=0.9, times_seen=sighting,
                        previous_stage=previous)
        stages.append(verdict.severity)
        previous = verdict.stage

    assert stages[0] == 0
    assert stages[-1] == 5, "a sustained strong finding does reach critical"
    for earlier, later in zip(stages, stages[1:]):
        assert later - earlier <= 1, "no stage may be skipped"


def test_a_stage_falls_as_soon_as_the_evidence_does():
    """Slow to stand down means a repaired machine reads severe for a week,
    and the next real finding on it is ignored."""
    verdict = grade(score=0.05, confidence=0.9, times_seen=20,
                    previous_stage="critical")
    assert verdict.stage == "normal"
    assert verdict.fell is True
    assert "repaired" in verdict.reason


def test_repetition_cannot_promote_a_weak_signal():
    """A weak pattern seen often is a weak pattern seen often."""
    previous = None
    for sighting in range(1, 30):
        verdict = grade(score=0.95, confidence=0.25, times_seen=sighting,
                        previous_stage=previous)
        previous = verdict.stage
    assert verdict.severity <= STAGES.index("watch")
    assert verdict.ceiling == "watch"


def test_the_ceiling_is_the_lower_of_score_and_confidence():
    assert ceiling_for(0.95, 0.95) == "critical"
    assert ceiling_for(0.95, 0.25) == "watch", "confidence caps it"
    assert ceiling_for(0.16, 0.95) == "watch", "and so does score"


def test_a_held_stage_says_what_it_is_waiting_for():
    verdict = grade(score=0.95, confidence=0.9, times_seen=2,
                    previous_stage="watch")
    assert verdict.reason
    assert str(verdict.ceiling).replace("_", " ") in verdict.reason.lower() \
        or "sighting" in verdict.reason
