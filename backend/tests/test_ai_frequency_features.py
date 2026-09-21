"""Thirteen frequency-domain features — VIK-019.

The sideband search is most of this file, because it is the part that took
four corrections to get right and every one of them was a wrong answer that
looked reasonable:

  one line of spacing on six of eight signatures   (window skirt)
  181 Hz on the outer race                         (a multiple, not the fundamental)
  95.2 Hz where BPFO is 89.25                      (an arbitrary candidate grid)
  21.88 Hz where the shaft turns at 25             (family rule landing a bin low)

None of those raises an error. Each produces a number that a rule downstream
would read as a mechanism, and 7.12X names no bearing anyone has heard of.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.ai.fault_harness import FS_HZ, SHAFT_HZ, generate
from app.ai.frequency_features import (
    FREQUENCY_FEATURE_CODES,
    MAX_HARMONIC,
    PRESENCE_RATIO,
    SIDEBAND_PRESENCE_RATIO,
    extract_frequency_features,
)

BPFO_ORDER = 3.57
LINE_HZ = FS_HZ / 8192           # 3.125 Hz


def spectrum_of(samples):
    x = np.asarray(samples, dtype=float)
    x = x - x.mean()
    window = np.hanning(x.size)
    amps = np.abs(np.fft.rfft(x * window)) * 2.0 / window.sum()
    return np.fft.rfftfreq(x.size, d=1.0 / FS_HZ), amps


def features(name, shaft=SHAFT_HZ, previous=None):
    samples, _ = generate(name)
    freqs, amps = spectrum_of(samples)
    return extract_frequency_features(
        freqs, amps, shaft_hz=shaft, previous_dominant_hz=previous
    )


def value(name, code, **kw):
    return features(name, **kw)[code]["value"]


# ------------------------------------------------------------- shape --

def test_all_thirteen_are_computed():
    result = features("unbalance")
    assert set(result) == set(FREQUENCY_FEATURE_CODES)
    assert len(FREQUENCY_FEATURE_CODES) == 13


def test_it_cannot_compute_a_second_fft():
    """The ticket's "one spectrum per segment and fan out", enforced by the
    signature: the function takes freqs and amplitudes, never samples."""
    import inspect
    parameters = list(inspect.signature(extract_frequency_features).parameters)
    assert parameters[:2] == ["freqs", "amplitudes"]
    assert "samples" not in parameters


@pytest.mark.parametrize("name", [
    "healthy_horizontal", "unbalance", "misalignment", "bearing_outer_race",
    "looseness", "bearing_inner_race", "cavitation",
])
def test_nothing_is_infinite_or_nan(name):
    for code, payload in features(name).items():
        assert np.isfinite(payload["value"]), f"{name}/{code}"


def test_a_spectrum_too_short_returns_zeros_with_a_reason():
    """Zeros with a note, never missing keys: an absent key breaks a caller."""
    result = extract_frequency_features(np.array([0.0, 1.0]), np.array([0.0, 1.0]))
    assert set(result) == set(FREQUENCY_FEATURE_CODES)
    assert all(p["value"] == 0.0 for p in result.values())
    assert all("too short" in p["metadata"].get("note", "") for p in result.values())


# ---------------------------------------------------- dominant frequency --

def test_the_dominant_line_is_where_each_fault_puts_it():
    assert value("unbalance", "dominant_frequency") == pytest.approx(25.0, abs=LINE_HZ)
    assert value("misalignment", "dominant_frequency") == pytest.approx(50.0, abs=LINE_HZ)
    # the bearing's energy is on its resonance, not its defect rate
    assert value("bearing_outer_race", "dominant_frequency") == pytest.approx(4200, rel=0.02)


def test_prominence_separates_a_tone_from_the_tallest_noise():
    assert value("unbalance", "dominant_prominence") > 500
    assert value("cavitation", "dominant_prominence") < 100


# ----------------------------------------------------------- harmonics --

def test_shaft_faults_put_their_energy_on_harmonics_and_bearings_do_not():
    """The core split. Unbalance, misalignment and looseness are shaft-related
    and land on integer orders; a bearing defect is not an integer multiple of
    anything, so almost none of its energy is on them."""
    for shaft_fault in ("unbalance", "misalignment", "looseness"):
        assert value(shaft_fault, "harmonic_energy_ratio") > 0.4
    assert value("bearing_outer_race", "harmonic_energy_ratio") < 0.1


def test_looseness_shows_the_longest_harmonic_family():
    assert value("looseness", "harmonic_count") >= value("unbalance", "harmonic_count")


def test_harmonics_cannot_be_counted_without_a_shaft_speed():
    """Reporting 0 while implying "none found" would be a lie; the metadata
    records that no shaft speed was supplied."""
    result = features("looseness", shaft=None)
    assert result["harmonic_count"]["value"] == 0.0
    assert result["harmonic_count"]["metadata"]["shaft_hz"] is None


def test_the_harmonic_search_stops_where_it_says_it_does():
    assert features("looseness")["harmonic_count"]["metadata"]["searched_orders"] == MAX_HARMONIC


# ----------------------------------------------------------- sidebands --

def test_the_outer_race_sideband_spacing_is_bpfo():
    """The result that makes bearing diagnosis possible: a 4.2 kHz carrier
    modulated at the defect rate. Within a line of 3.57X."""
    spacing = value("bearing_outer_race", "sideband_spacing")
    assert spacing / SHAFT_HZ == pytest.approx(BPFO_ORDER, abs=0.1)


def test_misalignment_shows_shaft_rate_sidebands_on_its_2x_carrier():
    spacing = value("misalignment", "sideband_spacing")
    assert spacing / SHAFT_HZ == pytest.approx(1.0, abs=0.05)


def test_window_skirt_is_not_reported_as_a_sideband():
    """The first bug. A strong tone puts symmetric skirts on the bins beside
    it -- exactly the shape a sideband search looks for -- and that reported
    one line of spacing on six of eight signatures, including both healthy
    ones."""
    for clean in ("healthy_horizontal", "healthy_vertical", "unbalance",
                  "looseness", "cavitation"):
        assert value(clean, "sideband_spacing") == 0.0, (
            f"{clean} has no modulation of its dominant line and must "
            f"report no sidebands"
        )


def test_a_pair_barely_above_the_floor_names_nothing():
    """A weaker version of the same bug, which survived the first fix.

    At the general 6x presence bar the looseness signature reported 9.5 Hz of
    spacing on its 25 Hz line -- order 0.38, which corresponds to no
    mechanism. Sidebands are read as evidence of a specific cause, so the bar
    for them is higher than the bar for a line merely existing.
    """
    assert SIDEBAND_PRESENCE_RATIO > PRESENCE_RATIO
    assert value("looseness", "sideband_spacing") == 0.0


def test_spacing_and_energy_agree_about_whether_there_are_sidebands():
    """Reporting energy in sidebands that have no spacing, or the reverse,
    would let two rules reading the same spectrum disagree."""
    for name in ("healthy_horizontal", "unbalance", "misalignment",
                 "looseness", "bearing_outer_race", "cavitation"):
        result = features(name)
        has_spacing = result["sideband_spacing"]["value"] > 0
        has_energy = result["sideband_energy_ratio"]["value"] > 0
        assert has_spacing == has_energy, name


def test_the_fundamental_spacing_is_reported_not_a_multiple():
    """The second bug. Modulation produces a family, any member of which can
    be loudest; taking the loudest returned 181 Hz on the outer race -- twice
    BPFO, reading as order 7.12, which matches no bearing."""
    spacing = value("bearing_outer_race", "sideband_spacing")
    assert spacing < 120.0, f"{spacing:.1f} Hz looks like a multiple of BPFO"


def test_a_sideband_lands_on_a_real_line():
    """The third bug. An arbitrary 40-step candidate grid cannot hit the
    actual spacing: it reported 95.2 Hz for a BPFO of 89.25."""
    spacing = value("bearing_outer_race", "sideband_spacing")
    assert spacing % LINE_HZ == pytest.approx(0.0, abs=0.01) or \
        spacing == pytest.approx(SHAFT_HZ, abs=0.01)


def test_a_sideband_on_a_resonance_slope_is_still_found():
    """The fourth bug, in the other direction. Requiring a strict local
    maximum rejected the BPFO sidebands, because they sit on the slope of the
    resonance hump and one neighbour is always higher. That turned a correct
    87.5 Hz into 178 Hz."""
    assert value("bearing_outer_race", "sideband_spacing") > 0.0


# --------------------------------------------------- shape of the spectrum --

def test_broadband_faults_raise_entropy_and_tonal_ones_lower_it():
    """Entropy is what separates "something is ringing" from "everything got
    noisier"."""
    assert value("cavitation", "spectral_entropy") > 0.7
    assert value("unbalance", "spectral_entropy") < 0.3


def test_narrowband_ratio_is_the_mirror_of_entropy():
    assert value("unbalance", "narrowband_ratio") > 0.9
    assert value("cavitation", "narrowband_ratio") < 0.3


def test_the_centroid_rises_with_high_frequency_content():
    """One of the earliest bearing signs, and it costs nothing to compute."""
    assert value("bearing_outer_race", "spectral_centroid") > 1000
    assert value("unbalance", "spectral_centroid") < 200


# --------------------------------------------------------------- drift --

def test_drift_is_measured_against_a_previous_capture():
    drift = value("unbalance", "peak_drift", previous=24.0)
    assert drift == pytest.approx((25.0 - 24.0) / 24.0, abs=0.01)


def test_without_a_previous_capture_zero_means_unknown_not_unchanged():
    """Drift is a change between two captures. Reporting 0.0 as though it
    meant "steady" would read as evidence of stability."""
    result = features("unbalance")
    assert result["peak_drift"]["value"] == 0.0
    assert "unknown, not unchanged" in result["peak_drift"]["metadata"]["basis"]


def test_the_inner_race_limit_of_a_raw_spectrum_is_real_and_pinned():
    """Not a bug -- the boundary of what these features can see.

    An inner-race defect IS modulated at shaft rate, and the harness test
    suite confirms those sidebands exist around BPFI. They are invisible here
    because the loudest line in the RAW spectrum of that channel is the 25 Hz
    shaft line, and there is no modulation around THAT. Seeing them needs the
    envelope of the resonance band, which is VIK-020.

    Pinned so that nobody reads a zero here as "this bearing has no
    modulation", and so that VIK-020 has a test that changes when it lands.
    """
    result = features("bearing_inner_race")
    assert result["sideband_spacing"]["value"] == 0.0
    assert result["dominant_frequency"]["value"] == pytest.approx(SHAFT_HZ, abs=LINE_HZ)


def test_haystack_and_broadband_rise_together_on_a_raised_floor():
    """The pair that says "everything got noisier" rather than "one thing is
    ringing". Cavitation is the case; unbalance is the control."""
    cavitation = features("cavitation")
    unbalance = features("unbalance")
    assert cavitation["haystack_score"]["value"] > 0.85
    assert unbalance["haystack_score"]["value"] < 0.6
    assert (cavitation["broadband_noise"]["value"]
            > 5 * unbalance["broadband_noise"]["value"])


def test_the_dominant_line_carries_its_order_when_the_shaft_speed_is_known():
    """A frequency in hertz means nothing without the speed it is relative to.
    50 Hz is 2X at 1500 rpm and 1X at 3000."""
    assert features("misalignment")["dominant_frequency"]["metadata"]["order"] == \
        pytest.approx(2.0, abs=0.01)
    assert features("misalignment", shaft=None)["dominant_frequency"]["metadata"]["order"] is None


def test_the_sideband_spacing_carries_its_order_too():
    order = features("bearing_outer_race")["sideband_spacing"]["metadata"]["order"]
    assert order == pytest.approx(BPFO_ORDER, abs=0.1)


# ================================================================== #
#  Guards the harness does not exercise
#
#  Mutation testing found seven guards the eight harness signatures
#  cannot reach: the harness's shaft rate sits exactly on the line grid,
#  its sidebands are never buried under their own harmonics, and its
#  spectra carry no integration drift. A guard nothing reaches is a
#  guard nobody would notice breaking, so these build the spectrum
#  directly instead.
# ================================================================== #

RESOLUTION_HZ = 3.125
FLOOR = 0.001


def blank_spectrum(top_hz=6000.0):
    freqs = np.arange(0.0, top_hz, RESOLUTION_HZ)
    return freqs, np.full(freqs.size, FLOOR)


def put(freqs, amps, hz, amplitude):
    """A line at the nearest bin to hz, plus the skirt a real window leaves."""
    idx = int(np.argmin(np.abs(freqs - hz)))
    amps[idx] = amplitude
    for offset, share in ((1, 0.30), (2, 0.06)):
        for neighbour in (idx - offset, idx + offset):
            if 0 <= neighbour < amps.size:
                amps[neighbour] = max(amps[neighbour], amplitude * share)
    return amps


def test_a_stronger_harmonic_pair_does_not_hide_the_fundamental_spacing():
    """The family rule, which the harness no longer reaches.

    Modulation produces pairs at the modulating frequency AND its multiples,
    and the second pair is often the loudest. Taking the loudest reports a
    multiple: on an earlier build that returned 181 Hz for an 89 Hz BPFO,
    reading as order 7.24, which matches no bearing anyone would recognise.

    Here the 200 Hz pair is deliberately four times the 100 Hz one.
    """
    freqs, amps = blank_spectrum()
    put(freqs, amps, 1000.0, 1.0)
    put(freqs, amps, 900.0, 0.05)
    put(freqs, amps, 1100.0, 0.05)
    put(freqs, amps, 800.0, 0.20)
    put(freqs, amps, 1200.0, 0.20)

    spacing = extract_frequency_features(freqs, amps)["sideband_spacing"]["value"]
    assert spacing == 100.0, (
        f"{spacing} Hz -- the loudest pair is at 200 Hz, the modulating "
        f"frequency is 100, and 100 is exactly on a line"
    )


def test_a_symmetric_hump_is_not_a_sideband_pair():
    """The local-rise guard, which the harness reaches only through its
    bounds check.

    A raised, rounded region either side of a carrier -- late bearing damage,
    cavitation -- is symmetric and clears the amplitude floor, which is the
    whole shape a sideband search matches on. It is not modulation, and
    naming a spacing for it invents a mechanism.
    """
    freqs, amps = blank_spectrum()
    put(freqs, amps, 1000.0, 1.0)
    hump = ((freqs > 700) & (freqs < 900)) | ((freqs > 1100) & (freqs < 1300))
    amps[hump] = 0.05

    result = extract_frequency_features(freqs, amps)
    assert result["sideband_spacing"]["value"] == 0.0
    assert result["sideband_energy_ratio"]["value"] == 0.0


def test_a_shaft_rate_off_the_line_grid_is_reported_exactly():
    """A real machine's shaft rate does not land on a line: 1480 rpm is
    24.667 Hz and the spectrum's lines are 3.125 Hz apart. Reporting the
    nearest line, 25.0, reads as order 1.013, and a rule looking for 1X
    modulation does not fire on 1.013.

    The search handles this by making the shaft rate itself a candidate
    rather than by rounding a result back onto it.
    """
    shaft = 24.667
    freqs, amps = blank_spectrum()
    put(freqs, amps, 1000.0, 1.0)
    put(freqs, amps, 1000.0 - shaft, 0.08)
    put(freqs, amps, 1000.0 + shaft, 0.08)

    result = extract_frequency_features(freqs, amps, shaft_hz=shaft)
    assert result["sideband_spacing"]["value"] == pytest.approx(shaft, abs=0.001)
    assert result["sideband_spacing"]["metadata"]["order"] == pytest.approx(1.0, abs=0.001)


def test_a_divisor_with_no_family_behind_it_is_not_the_fundamental():
    """Contiguity, which is what separates a fundamental from a coincidence.

    75 divides 300 exactly, so a rule that only checked divisibility would
    call it the spacing. It is not: there are no pairs at 150 or 225, so 75
    is one isolated pair that happens to divide, while 100 has 200 and 300
    behind it.
    """
    freqs, amps = blank_spectrum()
    put(freqs, amps, 1000.0, 1.0)
    for offset, amplitude in ((100, 0.05), (200, 0.20), (300, 0.40)):
        put(freqs, amps, 1000.0 - offset, amplitude)
        put(freqs, amps, 1000.0 + offset, amplitude)
    put(freqs, amps, 1000.0 - 75, 0.05)
    put(freqs, amps, 1000.0 + 75, 0.05)

    spacing = extract_frequency_features(freqs, amps)["sideband_spacing"]["value"]
    assert spacing == 100.0


def test_a_long_family_still_reports_its_fundamental():
    """Why the search is not capped at a few orders.

    A heavily modulated bearing produces a long family, and the loudest pair
    can be well up it. Capping at six orders rejects the true fundamental
    here -- the strongest pair is the eighth -- and returns twice it at order
    four: a multiple reported as the spacing, which is the failure the family
    rule exists to prevent.
    """
    spacing_hz = 13 * RESOLUTION_HZ          # 40.625, exactly on the grid
    freqs, amps = blank_spectrum()
    put(freqs, amps, 2000.0, 1.0)
    amplitudes = {1: 0.03, 2: 0.04, 3: 0.05, 4: 0.06,
                  5: 0.07, 6: 0.08, 7: 0.10, 8: 0.30}
    for order, amplitude in amplitudes.items():
        put(freqs, amps, 2000.0 - order * spacing_hz, amplitude)
        put(freqs, amps, 2000.0 + order * spacing_hz, amplitude)

    spacing = extract_frequency_features(freqs, amps)["sideband_spacing"]["value"]
    assert spacing == spacing_hz, (
        f"{spacing} Hz -- the loudest pair is the eighth, but the modulating "
        f"frequency is {spacing_hz}"
    )


def test_a_family_whose_spacing_falls_between_lines_is_still_recognised():
    """The realistic case, and the one that decides how a family is checked.

    A defect rate is not a multiple of the line spacing, so each member of
    its family rounds to its own nearest line and the error against an exact
    multiple grows with the order: the tenth member of a 37 Hz family sits
    6 Hz from 10 x 37.5, which is two lines, and a check against the
    multiple rejects the family outright.

    The error in the fundamental each member IMPLIES does not grow -- that
    tenth member implies 36.9 Hz. So each member is checked by what it
    implies, not by how far it is from the multiple.
    """
    true_spacing = 37.0
    freqs, amps = blank_spectrum()
    put(freqs, amps, 2000.0, 1.0)
    for order in range(1, 11):
        amplitude = 0.30 if order == 10 else 0.04
        put(freqs, amps, 2000.0 - order * true_spacing, amplitude)
        put(freqs, amps, 2000.0 + order * true_spacing, amplitude)

    spacing = extract_frequency_features(freqs, amps)["sideband_spacing"]["value"]
    assert spacing == pytest.approx(true_spacing, abs=RESOLUTION_HZ), (
        f"{spacing} Hz for a family spaced {true_spacing} Hz -- the nearest "
        f"line is all the spectrum can resolve, but this is not it"
    )


def test_noise_alone_produces_no_harmonics():
    """The presence bar. Without it every order counts as found, and a
    healthy machine reports a ten-harmonic family."""
    rng = np.random.default_rng(0)
    freqs = np.arange(0.0, 6000.0, RESOLUTION_HZ)
    amps = rng.rayleigh(scale=0.001, size=freqs.size)

    result = extract_frequency_features(freqs, amps, shaft_hz=25.0)
    assert result["harmonic_count"]["value"] == 0.0
    assert result["harmonic_energy_ratio"]["value"] == 0.0


def test_the_search_reaches_the_tenth_order():
    """Ten, as a literal. Asserting against MAX_HARMONIC alone would follow
    the constant wherever it went."""
    assert MAX_HARMONIC == 10
    freqs, amps = blank_spectrum()
    for order in range(1, 13):
        put(freqs, amps, order * 25.0, 1.0)
    result = extract_frequency_features(freqs, amps, shaft_hz=25.0)
    assert result["harmonic_count"]["value"] == 10.0


def test_a_standing_dc_term_is_not_treated_as_vibration():
    """The DC guard.

    At a 3.125 Hz line spacing there is nothing below 2 Hz except bin zero,
    so that bin is the whole of what this guard removes -- and bin zero is
    the channel's standing bias, which on the real gateway reaches -0.145 g
    on ch7. Left in, it is the largest thing in the spectrum: the dominant
    frequency comes back as 0 Hz and the centre of mass collapses onto it.
    """
    freqs, amps = blank_spectrum()
    amps[0] = 50.0                      # sensor bias, not vibration
    put(freqs, amps, 2000.0, 1.0)

    result = extract_frequency_features(freqs, amps)
    assert result["dominant_frequency"]["value"] == pytest.approx(2000.0, abs=RESOLUTION_HZ)
    assert result["spectral_centroid"]["value"] > 1500, (
        f"bias pulled the centroid to {result['spectral_centroid']['value']:.0f} Hz"
    )


def test_prominence_is_measured_against_the_median_line_not_the_mean():
    """A few strong lines pull the mean up and leave the median alone. Against
    the mean, the more tonal a spectrum is the less prominent its peak
    measures -- backwards."""
    freqs, amps = blank_spectrum()
    put(freqs, amps, 1000.0, 1.0)
    for hz in (200.0, 400.0, 600.0, 800.0):
        put(freqs, amps, hz, 0.5)

    result = extract_frequency_features(freqs, amps)
    median = float(np.median(amps[freqs > 2.0]))
    mean = float(np.mean(amps[freqs > 2.0]))
    assert mean > 2 * median, "this spectrum does not separate the two"
    assert result["dominant_prominence"]["value"] == pytest.approx(1.0 / median, rel=1e-6)
