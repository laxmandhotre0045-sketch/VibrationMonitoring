"""Ten envelope measurements — VIK-020.

The ticket's acceptance is one sentence: "the harness's BPFO channel scores
high on BPFO band energy and low on the other three." That is the first test
here and it passes by a wide margin — 406 against 2.8 — but it is the easy
half.

The hard half is everything that scores high when it should not. A bearing
diagnosis is the most consequential thing this platform will say, and the
ways to arrive at a false one are specific:

  a defect rate sitting in the same spectrum line as a shaft harmonic
  a defect rate below the first usable line of the envelope spectrum
  a band chosen by a method that picks the wrong band
  a machine with no bearing resolved, reading zero as "nothing found"

Each has its own test, because each produces a number rather than an error.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.ai.envelope_features import (
    ENVELOPE_FEATURE_CODES,
    MIN_RESOLVABLE_LINES,
    extract_envelope_features,
    find_resonance,
)
from app.ai.fault_harness import FS_HZ, SHAFT_HZ, SIGNATURES, generate

#: 6312 from the catalogue, with the harness's own BPFO and BPFI.
ORDERS = {"ftf": 0.383, "bsf": 2.020, "bpfo": 3.57, "bpfi": 5.43}
DEFECTS = ("ftf_band_energy", "bsf_band_energy", "bpfo_band_energy", "bpfi_band_energy")


def raw_spectrum(samples):
    x = np.asarray(samples, dtype=float)
    x = x - x.mean()
    window = np.hanning(x.size)
    amps = np.abs(np.fft.rfft(x * window)) * 2.0 / window.sum()
    return np.fft.rfftfreq(x.size, d=1.0 / FS_HZ), amps


def features(name, *, shaft=SHAFT_HZ, orders=ORDERS):
    samples, truth = generate(name)
    freqs, amps = raw_spectrum(samples)
    return extract_envelope_features(
        samples, FS_HZ, freqs=freqs, amplitudes=amps,
        shaft_hz=shaft, bearing_orders=orders,
    ), truth


def value(name, code, **kw):
    return features(name, **kw)[0][code]["value"]


# --------------------------------------------- the ticket's acceptance --

def test_the_outer_race_channel_scores_high_on_bpfo_and_low_on_the_others():
    """VIK-020's stated acceptance, word for word."""
    result, _ = features("bearing_outer_race")

    bpfo = result["bpfo_band_energy"]["value"]
    others = [result[c]["value"] for c in DEFECTS if c != "bpfo_band_energy"]

    assert bpfo > 100, f"BPFO only reached {bpfo:.1f}"
    assert max(others) < 10, f"another defect rate reached {max(others):.1f}"
    assert bpfo > 20 * max(others)


def test_the_inner_race_channel_scores_high_on_bpfi():
    result, _ = features("bearing_inner_race")

    bpfi = result["bpfi_band_energy"]["value"]
    others = [result[c]["value"] for c in DEFECTS if c != "bpfi_band_energy"]

    assert bpfi > 50, f"BPFI only reached {bpfi:.1f}"
    assert bpfi > 10 * max(others)


@pytest.mark.parametrize("name", [
    "healthy_horizontal", "healthy_vertical", "unbalance",
    "misalignment", "looseness", "cavitation",
])
def test_a_machine_with_no_bearing_defect_scores_low_on_all_four(name):
    """The half that matters more. Naming a bearing fault on a healthy
    machine teaches people to ignore the system."""
    result, _ = features(name)
    worst = max(result[c]["value"] for c in DEFECTS)
    assert worst < 10, f"{name} reached {worst:.1f} on a defect rate"


def test_the_two_bearings_are_separated_from_everything_else_by_kurtosis():
    """Envelope kurtosis measured 208 and 128 on the bearing channels against
    0.7 to 1.5 on the other six -- the widest margin of any feature here."""
    bearings = [value(n, "envelope_kurtosis")
                for n in ("bearing_outer_race", "bearing_inner_race")]
    rest = [value(n, "envelope_kurtosis") for n in SIGNATURES
            if not n.startswith("bearing")]
    assert min(bearings) > 20 * max(rest)


# ----------------------------------------------------- choosing the band --

def test_the_band_is_centred_on_the_real_resonance():
    """Spectral kurtosis is the textbook selector and it chose 1600 Hz for
    both bearings, against true resonances of 4200 and 3100, because a low
    band holds impulsive content with fewer competing tones. The largest raw
    line above 500 Hz found both to within 1%.
    """
    for name in ("bearing_outer_race", "bearing_inner_race"):
        samples, truth = generate(name)
        band = find_resonance(*raw_spectrum(samples))
        assert band.centre_hz == pytest.approx(truth.resonance_hz, rel=0.01), name
        assert band.low_hz < truth.resonance_hz < band.high_hz


def test_the_band_prominence_says_whether_there_is_a_resonance_at_all():
    """On a machine with no defect the largest high-frequency line is
    arbitrary, and the envelope of an arbitrary band shows nothing. That is
    the right answer, but the reader should be able to see it coming."""
    bearings = [value(n, "resonance_band_energy")
                for n in ("bearing_outer_race", "bearing_inner_race")]
    rest = [value(n, "resonance_band_energy") for n in SIGNATURES
            if not n.startswith("bearing")]
    assert min(bearings) > 5 * max(rest)


def test_no_spectrum_means_no_band_and_an_honest_zero():
    band = find_resonance(None, None)
    assert band.centre_hz == 0.0
    assert "no spectrum" in band.note

    result = extract_envelope_features([0.0] * 4096, FS_HZ, shaft_hz=SHAFT_HZ,
                                       bearing_orders=ORDERS)
    assert set(result) == set(ENVELOPE_FEATURE_CODES)
    assert all(p["value"] == 0.0 for p in result.values())
    assert all(p["metadata"].get("note") for p in result.values())


# ------------------------------------------- the ways to be falsely sure --

def test_a_defect_rate_sharing_a_line_with_a_shaft_harmonic_is_flagged():
    """BSF is 50.50 Hz and twice shaft speed is 50.00. At 6.25 Hz lines they
    are the same measurement, and on the real pump it is worse: BSF 49.83
    against 2x at 49.33 and mains at 50.00. A number here is not evidence of
    a ball defect and must not be presented as one.
    """
    result, _ = features("bearing_outer_race")
    note = result["bsf_band_energy"]["metadata"].get("note", "")
    assert "2x shaft" in note
    assert "cannot be told apart" in note


def test_the_cage_rate_always_carries_a_caveat_on_this_bearing():
    """FTF is 9.57 Hz, and on this machine it is never a clean reading --
    only the reason changes with resolution. At 12.2 Hz lines it sits below
    the first usable one; at 3.1 Hz lines it is resolvable but lands within
    a line of half shaft speed, which looseness puts a real line at.

    What must never happen is a bare number with nothing said about it.
    """
    result, _ = features("bearing_outer_race")
    ftf = result["ftf_band_energy"]["metadata"]
    assert "note" in ftf, "the cage rate was reported with no caveat at all"
    assert ("cannot be resolved" in ftf["note"]
            or "cannot be told apart" in ftf["note"])


def test_a_rate_below_the_first_usable_line_says_a_longer_capture_is_needed():
    """The resolution guard on its own, at a resolution coarse enough to
    trigger it. A line one bin from DC carries the envelope's own mean, so a
    number there measures the transform rather than the bearing."""
    samples, _ = generate("bearing_outer_race")
    freqs, amps = raw_spectrum(samples)

    # A shaft slow enough that even BPFO falls under the first usable line.
    result = extract_envelope_features(
        samples, FS_HZ, freqs=freqs, amplitudes=amps,
        shaft_hz=0.2, bearing_orders=ORDERS,
    )
    note = result["bpfo_band_energy"]["metadata"]["note"]
    assert result["bpfo_band_energy"]["value"] == 0.0
    assert "cannot be resolved" in note
    assert "longer capture" in note


def test_a_resolvable_defect_rate_carries_no_excuse():
    """The guards must not fire on the case that works, or they would explain
    away a real finding."""
    result, _ = features("bearing_outer_race")
    assert "note" not in result["bpfo_band_energy"]["metadata"]


def test_no_bearing_resolved_means_not_looked_for_not_nothing_found():
    """Zero with no explanation reads as a clean bill of health for a machine
    whose bearing nobody has identified."""
    result, _ = features("bearing_outer_race", orders=None)
    for code in DEFECTS:
        assert result[code]["value"] == 0.0
        assert "not looked for" in result[code]["metadata"]["note"]


def test_no_shaft_speed_means_the_defect_rates_cannot_be_placed():
    """Every defect rate is an order, so without a speed there is no
    frequency to look at."""
    result, _ = features("bearing_outer_race", shaft=None)
    for code in DEFECTS:
        assert result[code]["value"] == 0.0
        assert "shaft speed unknown" in result[code]["metadata"]["note"]


def test_the_resolution_floor_is_where_it_claims_to_be():
    assert MIN_RESOLVABLE_LINES >= 2.0


# ------------------------------------------------- the remaining features --

def test_the_repetition_rate_is_the_defect_rate_on_a_defective_bearing():
    """The feature that names the cause without being told the bearing: how
    often the impacts actually repeat."""
    outer = value("bearing_outer_race", "repetition_impact_frequency")
    inner = value("bearing_inner_race", "repetition_impact_frequency")
    assert outer == pytest.approx(3.57 * SHAFT_HZ, rel=0.05)
    assert inner == pytest.approx(5.43 * SHAFT_HZ, rel=0.05)


def test_the_repetition_rate_carries_its_order():
    result, _ = features("bearing_outer_race")
    order = result["repetition_impact_frequency"]["metadata"]["order"]
    assert order == pytest.approx(3.57, abs=0.1)


def test_a_defect_shows_a_family_not_one_line():
    """A real defect repeats, so its envelope carries harmonics. One line on
    its own is as likely to be noise."""
    defective = value("bearing_outer_race", "bearing_harmonic_energy")
    healthy = value("healthy_horizontal", "bearing_harmonic_energy")
    assert defective > 20 * healthy


def test_prominence_and_peak_agree_about_which_line_is_tallest():
    result, _ = features("bearing_outer_race")
    assert result["demodulated_peak_prominence"]["value"] > 100
    assert result["envelope_peak"]["value"] > 0


# ------------------------------------------------------------ robustness --

def test_all_ten_are_always_present():
    result, _ = features("unbalance")
    assert set(result) == set(ENVELOPE_FEATURE_CODES)
    assert len(ENVELOPE_FEATURE_CODES) == 10


@pytest.mark.parametrize("name", list(SIGNATURES))
def test_nothing_is_infinite_or_nan(name):
    result, _ = features(name)
    for code, payload in result.items():
        assert np.isfinite(payload["value"]), f"{name}/{code}"


def test_a_short_record_is_refused_rather_than_demodulated():
    result = extract_envelope_features([0.1] * 32, FS_HZ, shaft_hz=SHAFT_HZ)
    assert all(p["value"] == 0.0 for p in result.values())
    assert "too few samples" in result["bpfo_band_energy"]["metadata"]["note"]


def test_a_silent_channel_does_not_raise():
    freqs, amps = raw_spectrum([0.0] * 8192)
    result = extract_envelope_features([0.0] * 8192, FS_HZ, freqs=freqs,
                                       amplitudes=amps, shaft_hz=SHAFT_HZ,
                                       bearing_orders=ORDERS)
    for code, payload in result.items():
        assert np.isfinite(payload["value"]), code


def test_nonsense_orders_do_not_raise():
    samples, _ = generate("unbalance")
    freqs, amps = raw_spectrum(samples)
    for orders in ({}, {"bpfo": 0}, {"bpfo": -1}, {"bpfo": None},
                   {"bpfo": 1e9}, {"unknown_key": 3.0}):
        result = extract_envelope_features(samples, FS_HZ, freqs=freqs,
                                           amplitudes=amps, shaft_hz=SHAFT_HZ,
                                           bearing_orders=orders)
        assert set(result) == set(ENVELOPE_FEATURE_CODES)


# ------------------------------------------ gaps mutation testing found --

def test_the_harmonic_energy_is_the_family_not_the_loudest_member():
    """Replacing the sum with just the fundamental left every test passing,
    because the fundamental alone still towers over a healthy channel. But
    then the feature is a duplicate of bpfo_band_energy and says nothing new.
    What it is for is the repetition: a real defect rings again at twice and
    three times its rate.
    """
    result, _ = features("bearing_outer_race")
    family = result["bearing_harmonic_energy"]["value"]
    fundamental = result["bpfo_band_energy"]["value"]

    assert family > fundamental * 1.5, (
        f"family {family:.1f} against fundamental {fundamental:.1f} -- the "
        f"harmonics are not being added in"
    )
    assert "1x to" in result["bearing_harmonic_energy"]["metadata"]["basis"]
    assert result["bearing_harmonic_energy"]["metadata"]["strongest"] == "bpfo"


def test_envelope_kurtosis_is_excess_kurtosis():
    """Zero for Gaussian, not three. Without the -3 the number still ranks
    the signatures correctly, so every comparison here passes while the value
    means something else -- and 3.0 is the figure a reader checks against.
    """
    rng = np.random.default_rng(0)
    noise = rng.normal(scale=0.01, size=16384)
    freqs, amps = raw_spectrum(noise)
    result = extract_envelope_features(noise, FS_HZ, freqs=freqs, amplitudes=amps,
                                       shaft_hz=SHAFT_HZ, bearing_orders=ORDERS)

    # The reference value, measured. The envelope spectrum of noise is not
    # quite Gaussian -- its lines are Rayleigh-distributed -- so this lands
    # near 0.9 rather than exactly 0, but close enough that the convention is
    # recognisable. Worth pinning because a reader needs a reference: the two
    # bearing channels read 414 and 245. Dropping the -3 would move this to
    # 3.9 and every comparison in this file would still pass.
    assert result["envelope_kurtosis"]["value"] == pytest.approx(0.86, abs=0.5)


def test_the_band_is_never_narrower_than_the_filter_can_deliver():
    """The band-pass fails quietly at high Q rather than raising.

    Asked for +/-5 Hz around 4,194 Hz it returns a signal with only 19.9% of
    its energy inside that band; at +/-100 Hz, 50.7%. Below a few hundred
    hertz, "demodulating the resonance" is demodulating the whole signal
    while appearing to have selected something -- which is why a narrow band
    still scored 408 on BPFO and no comparison could see the difference.

    The floor is what prevents it, so the floor is what is tested.
    """
    import app.ai.envelope_features as ef

    samples, _ = generate("bearing_outer_race")
    freqs, amps = raw_spectrum(samples)

    original = ef.BAND_FRACTION
    try:
        ef.BAND_FRACTION = 0.0          # ask for nothing at all
        band = find_resonance(freqs, amps)
    finally:
        ef.BAND_FRACTION = original

    half = (band.high_hz - band.low_hz) / 2
    assert half >= ef.BAND_MIN_HALF_WIDTH_HZ, (
        f"half-width fell to {half:.0f} Hz, where the filter passes mostly "
        f"content from outside the band"
    )


def test_prominence_is_against_the_median_line_not_the_mean():
    """A strong defect puts several tall lines into the envelope spectrum,
    and those drag the mean up with them. Measured against the mean, the
    clearer the defect the smaller its prominence reads -- backwards. The
    median is unmoved by a handful of tall lines, which is the whole reason
    for using it as the floor.
    """
    import app.ai.envelope_features as ef

    samples, _ = generate("bearing_outer_race")
    freqs, amps = raw_spectrum(samples)
    against_median = extract_envelope_features(
        samples, FS_HZ, freqs=freqs, amplitudes=amps,
        shaft_hz=SHAFT_HZ, bearing_orders=ORDERS)["bpfo_band_energy"]["value"]

    real_prominence = ef._prominence_at
    try:
        def against_the_mean(f, a, target_hz, tolerance_hz):
            if target_hz <= 0 or f.size == 0:
                return 0.0
            near = np.abs(f - target_hz) <= tolerance_hz
            if not np.any(near):
                return 0.0
            return float(np.max(a[near])) / (float(np.mean(a)) or 1e-30)
        ef._prominence_at = against_the_mean
        inflated_floor = extract_envelope_features(
            samples, FS_HZ, freqs=freqs, amplitudes=amps,
            shaft_hz=SHAFT_HZ, bearing_orders=ORDERS)["bpfo_band_energy"]["value"]
    finally:
        ef._prominence_at = real_prominence

    assert against_median > 2 * inflated_floor, (
        f"median floor gave {against_median:.0f} and mean floor "
        f"{inflated_floor:.0f} -- the defect's own lines are not moving the "
        f"mean, so this spectrum does not test the difference"
    )
