"""Observing the signal before naming anything — VIK-051.

A symptom is not a fault. `harmonic_series` says a series is present; it
does not say looseness. That separation is what lets a capture matching no
rule still have something said about it, which on this gateway -- whose
spectrum cannot separate its own bearing frequencies from shaft harmonics
-- is most captures.

**The hard part is sidebands, and these tests are mostly about that.** A
harmonic series is evenly spaced, and it is symmetric around every one of
its middle harmonics, so the two obvious ways to detect sidebands both fire
on every machine with harmonics. Three tests below pin the distinction that
actually works, and one of them is a signal that must produce *no* finding.

Every test drives real synthetic signals through the same peak finder the
pipeline uses, rather than hand-built peak lists. A hand-built list cannot
catch the case where the peak finder does not return what the symptom code
assumes.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.ai.symptoms import (
    MAX_HARMONIC_ORDER,
    MIN_CARRIER_DEPTH,
    MIN_HARMONICS,
    bearing_band_energy,
    detect,
    harmonic_series,
    impacting,
    sidebands,
    subharmonics,
)
from app.services.fault_context import peaks_from_spectrum

FS = 25_600.0
SECONDS = 4.0
SHAFT_HZ = 24.67


def peaks_of(signal: np.ndarray, shaft_hz: float | None = SHAFT_HZ):
    window = np.hanning(signal.size)
    mags = np.abs(np.fft.rfft(signal * window)) * 2 / np.sum(window)
    freqs = np.fft.rfftfreq(signal.size, 1 / FS)
    return peaks_from_spectrum(freqs, mags, shaft_hz=shaft_hz)


def timebase() -> np.ndarray:
    return np.arange(int(FS * SECONDS)) / FS


def tone(order: float, amplitude: float = 1.0) -> np.ndarray:
    return amplitude * np.sin(2 * np.pi * order * SHAFT_HZ * timebase())


# ------------------------------------------------------ harmonic series ---

def test_a_long_harmonic_series_is_reported_with_its_orders():
    signal = tone(1, 0.4) + sum(tone(k, 0.3 / k) for k in range(2, 9))
    found = harmonic_series(peaks_of(signal))

    assert found is not None
    assert found.detail["count"] >= MIN_HARMONICS
    # The evidence has to name the orders, not assert a boolean.
    assert "1x" in found.evidence[0] and "8x" in found.evidence[0]
    assert found.detail["orders"][:3] == [1, 2, 3]
    assert found.detail["starts_at"] == 1


def test_a_single_tone_is_not_a_harmonic_series():
    """Every rotating machine has 1x. Reporting that as a series would put
    the symptom on every capture the platform has ever taken."""
    assert harmonic_series(peaks_of(tone(1))) is None


def test_two_harmonics_are_not_a_series():
    """A peak and its octave is the most ordinary spectrum there is."""
    assert harmonic_series(peaks_of(tone(1) + tone(2, 0.5))) is None


# ------------------------------------------------------------ sidebands ---

def test_a_harmonic_series_is_not_reported_as_sidebands():
    """The false positive that made the first two implementations useless.

    A harmonic series is evenly spaced, and 2x and 4x straddle 3x exactly as
    sidebands straddle a carrier. Both of the obvious tests -- even spacing,
    and peaks on both sides -- fire here. If this ever starts returning a
    symptom, nearly every machine on the plant grows a sideband finding.
    """
    signal = tone(1, 0.4) + sum(tone(k, 0.3 / k) for k in range(2, 9))
    assert sidebands(peaks_of(signal), SHAFT_HZ) is None


def test_a_harmonic_series_peaking_mid_range_is_not_sidebands():
    """Isolates the downward-walk guard, which nothing else here does.

    Three rules can each reject a harmonic series, and in the ordinary case
    the other two get there first -- so removing the downward walk changed
    no test, which a mutation run showed. Working out why took a probe of
    every (carrier, spacing) pair the code considers:

      * the spacing is only ever measured from a peak *above* the carrier,
        so the topmost harmonic is never itself a carrier;
      * that leaves 7x as the only candidate, with 8x setting the spacing;
      * and in a series with a falling or rising profile, 8x or 1x
        out-amplitudes 7x, so the "a carrier dominates its own cluster"
        rule rejects it before the walk is consulted.

    Shaping the series to peak at 7x silences both of those. 7x is then the
    strongest line and is a genuine carrier candidate, and the only thing
    left between this and a false sideband finding is that the pattern
    carries on down to the fundamental instead of stopping.

    Gear wear that excites a mid-range harmonic produces a spectrum shaped
    like this, so it is not a contrived signal.
    """
    amplitudes = {1: 0.10, 2: 0.20, 3: 0.30, 4: 0.40,
                  5: 0.50, 6: 0.60, 7: 0.70, 8: 0.35}
    signal = sum(tone(k, a) for k, a in amplitudes.items())
    assert sidebands(peaks_of(signal), SHAFT_HZ) is None


def test_gear_mesh_modulated_at_running_speed_is_reported():
    t = timebase()
    mesh = 20 * SHAFT_HZ
    signal = (np.sin(2 * np.pi * mesh * t)
              * (1 + 0.5 * np.sin(2 * np.pi * SHAFT_HZ * t))
              + 0.2 * np.sin(2 * np.pi * SHAFT_HZ * t))
    found = sidebands(peaks_of(signal), SHAFT_HZ)

    assert found is not None
    assert found.detail["carrier_hz"] == pytest.approx(mesh, rel=0.02)
    assert found.detail["spacing_hz"] == pytest.approx(SHAFT_HZ, rel=0.05)
    assert found.detail["below"] >= 1 and found.detail["above"] >= 1
    # The spacing identifies which shaft the fault is on, so it has to be
    # stated rather than left for the reader to divide out.
    assert "running speed" in " ".join(found.evidence)


def test_a_carrier_must_sit_well_above_its_spacing():
    """A carrier three steps up cannot be told from the third harmonic of
    the spacing -- the downward walk has no room to stop early."""
    assert MIN_CARRIER_DEPTH >= 6


def test_pure_unbalance_has_no_sidebands():
    assert sidebands(peaks_of(tone(1) + tone(2, 0.05)), SHAFT_HZ) is None


# --------------------------------------------------------- subharmonics ---

def test_a_half_order_line_is_reported_as_sub_synchronous():
    signal = tone(1, 1.0) + tone(0.5, 0.6) + tone(2, 0.3)
    found = subharmonics(peaks_of(signal))

    assert found is not None
    assert found.detail["half_order"] is True
    assert found.detail["lowest_order"] == pytest.approx(0.5, abs=0.06)
    assert "half running speed" in " ".join(found.evidence)


def test_nothing_below_running_speed_reports_nothing():
    assert subharmonics(peaks_of(tone(1) + tone(2, 0.4))) is None


# ------------------------------------------------- the feature-based two ---

def test_impacting_wants_both_measures_to_agree():
    """Crest factor and kurtosis measure the same property differently, so
    a mildly raised one on its own is not evidence. At 4.0 crest -- a bar
    ordinary captures clear -- firing on either put this symptom on every
    channel examined, including a pure unbalance signature."""
    both = impacting({"crest_factor": 6.0, "kurtosis": 8.0})
    assert both is not None and both.detail["both_agree"] is True

    assert impacting({"crest_factor": 4.5, "kurtosis": 2.0}) is None
    assert impacting({"crest_factor": 2.0, "kurtosis": 4.8}) is None


def test_one_measure_far_past_its_threshold_still_counts():
    """Requiring both would throw away a real impact whose kurtosis happens
    to sit just under the line."""
    lone = impacting({"crest_factor": 9.0, "kurtosis": 2.0})
    assert lone is not None
    assert lone.detail["both_agree"] is False
    assert lone.detail["triggers"] == ["crest_factor"]


def test_a_missing_feature_reports_nothing_rather_than_not_impacting():
    """The distinction the whole platform turns on. No crest factor means
    the check could not run, and that must not read as a clean result."""
    assert impacting({}) is None
    assert impacting({"crest_factor": 6.0}) is None, "kurtosis was not measured"
    assert impacting({"kurtosis": 9.0}) is None, "crest factor was not measured"


def test_bearing_band_energy_needs_the_band_features():
    assert bearing_band_energy({}) is None


# -------------------------------------------------------------- detect ----

def test_detect_runs_every_check_and_keeps_only_what_fired():
    signal = tone(1, 0.4) + sum(tone(k, 0.3 / k) for k in range(2, 9))
    found = detect(peaks_of(signal), {"crest_factor": 6.0, "kurtosis": 8.0},
                   SHAFT_HZ)
    keys = {s.key for s in found}

    assert "harmonic_series" in keys
    assert "impacting" in keys
    assert "sidebands" not in keys, "a harmonic series is not sidebands"


def test_detect_without_features_still_reads_the_spectrum():
    """The features are optional and the spectrum symptoms must not depend
    on them -- a capture whose features failed still has a spectrum."""
    signal = tone(1, 0.4) + sum(tone(k, 0.3 / k) for k in range(2, 9))
    keys = {s.key for s in detect(peaks_of(signal), None, SHAFT_HZ)}
    assert "harmonic_series" in keys


def test_no_shaft_speed_leaves_the_order_based_checks_silent():
    """Every order in a symptom is computed against running speed. Without
    one there are no orders, and a harmonic series cannot be claimed."""
    signal = tone(1, 0.4) + sum(tone(k, 0.3 / k) for k in range(2, 9))
    found = detect(peaks_of(signal, shaft_hz=None), None, None)
    assert harmonic_series(peaks_of(signal, shaft_hz=None)) is None
    assert all(s.key != "harmonic_series" for s in found)


def test_every_symptom_carries_evidence_a_person_can_check():
    """The ticket's whole point: not a flag, a statement with numbers in it
    that an analyst can look at the spectrum and disagree with."""
    signal = tone(1, 0.4) + sum(tone(k, 0.3 / k) for k in range(2, 9))
    found = detect(peaks_of(signal), {"crest_factor": 6.0, "kurtosis": 8.0},
                   SHAFT_HZ)

    assert found
    for symptom in found:
        assert symptom.evidence, f"{symptom.key} fired with no evidence"
        assert any(any(ch.isdigit() for ch in line)
                   for line in symptom.evidence), (
            f"{symptom.key} states no numbers, so nobody can check it")
        assert symptom.as_dict()["key"] == symptom.key


# --------------------------- evidence that survived contact with real data --

def test_scattered_integers_are_not_a_harmonic_series():
    """Found by reprocessing a real capture, which reported "1x, 5x, 713x,
    877x" as four harmonics of running speed.

    The tolerance is a fraction of an order, so at 713x it spans about
    1.3 Hz out of 18 kHz and very nearly any peak up there satisfies it by
    chance. Scattered whole numbers are not a series: what makes a series
    diagnostic is the energy marching up in steps, which is what a clipped
    or struck waveform produces.
    """
    signal = tone(1) + tone(5, 0.6) + tone(13, 0.5) + tone(18, 0.4)
    assert harmonic_series(peaks_of(signal)) is None


def test_a_harmonic_must_be_a_low_multiple_of_running_speed():
    """Past about twenty orders the claim stops being diagnostic anyway --
    mesh frequencies and bearing bands live up there and have their own
    rules."""
    assert MAX_HARMONIC_ORDER <= 25

    high = sum(tone(k, 0.4) for k in range(MAX_HARMONIC_ORDER + 1,
                                           MAX_HARMONIC_ORDER + 6))
    assert harmonic_series(peaks_of(tone(1) + high)) is None


def test_a_series_that_does_not_start_near_1x_is_something_elses_fundamental():
    signal = sum(tone(k, 0.4) for k in range(6, 11))
    assert harmonic_series(peaks_of(signal)) is None


def test_a_run_starting_at_2x_still_counts():
    """Misalignment can suppress 1x almost entirely."""
    signal = sum(tone(k, 0.5) for k in range(2, 8))
    found = harmonic_series(peaks_of(signal))
    assert found is not None
    assert found.detail["starts_at"] == 2


def test_the_bearing_band_share_is_a_real_proportion():
    """Also found on a real capture, which printed "243378% of the
    envelope". A band energy divided by an envelope amplitude is not a
    ratio of anything -- the units do not cancel -- and a number like that
    tells a reader only that the platform is not checking its arithmetic.
    """
    found = bearing_band_energy({
        "bpfo_band_energy": 6.0, "bpfi_band_energy": 2.0,
        "bsf_band_energy": 1.0, "ftf_band_energy": 1.0,
        "envelope_rms": 1e-5,
    })

    assert found is not None
    text = " ".join(found.evidence)
    assert "60%" in text, "BPFO is 6 of the 10 units across the four bands"
    # Every percentage quoted must be one that can exist.
    import re
    for value in re.findall(r"(\d+)%", text):
        assert 0 <= int(value) <= 100, f"{value}% is not a proportion"


def test_one_bearing_band_alone_is_all_of_the_bearing_energy():
    found = bearing_band_energy({"bpfo_band_energy": 4.0})
    assert found is not None
    assert "100%" in " ".join(found.evidence)
