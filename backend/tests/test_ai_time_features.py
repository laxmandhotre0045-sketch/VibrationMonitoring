"""Thirteen time-domain features — VIK-018.

The ticket's acceptance is "all 13 computed per channel; tested against the
harness". Computing them is the easy half. What these tests check is that each
one separates the faults it is supposed to separate, because a feature that
moves for everything adds a column and no information.

Every expectation here was measured on the harness first and then written
down, not assumed. One of them came out backwards on the first attempt -- see
test_modulation_index_is_measured_at_shaft_rate.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.ai.fault_harness import FS_HZ, SHAFT_HZ, generate
from app.ai.time_features import (
    BURST_SIGMA,
    TIME_FEATURE_CODES,
    extract_time_features,
)


def features(name: str, shaft: float | None = SHAFT_HZ):
    samples, _ = generate(name)
    return extract_time_features(samples, FS_HZ, shaft_hz=shaft)


def value(name: str, code: str, shaft: float | None = SHAFT_HZ) -> float:
    return features(name, shaft)[code]["value"]


# ------------------------------------------------------ all thirteen --

def test_all_thirteen_are_computed():
    result = features("unbalance")
    assert set(result) == set(TIME_FEATURE_CODES)
    assert len(TIME_FEATURE_CODES) == 13


def test_every_feature_carries_a_unit():
    for payload in features("unbalance").values():
        assert payload["unit"]
        assert isinstance(payload["value"], float)


@pytest.mark.parametrize("name", [
    "healthy_horizontal", "healthy_vertical", "unbalance", "misalignment",
    "bearing_outer_race", "looseness", "bearing_inner_race", "cavitation",
])
def test_no_feature_is_infinite_or_nan_on_any_signature(name):
    for code, payload in features(name).items():
        assert np.isfinite(payload["value"]), f"{name}/{code} is not finite"


def test_a_silent_channel_produces_zeros_not_exceptions():
    """A disconnected sensor reads flat. Dividing by its zero spread must not
    raise, and must not produce an infinity that grades as critical."""
    flat = [0.0] * 1024
    result = extract_time_features(flat, FS_HZ, shaft_hz=SHAFT_HZ)
    for code, payload in result.items():
        assert np.isfinite(payload["value"]), f"{code} is not finite on a flat channel"


def test_too_few_samples_is_refused():
    with pytest.raises(ValueError):
        extract_time_features([1.0, 2.0], FS_HZ)


# --------------------------------------------- they separate the faults --

def test_impulsive_faults_raise_the_shape_factors():
    """Impulse and clearance factors are peak-over-average ratios, so they
    rise for impacting and stay put for a steady sinusoidal fault."""
    bearing = value("bearing_outer_race", "impulse_factor")
    unbalance = value("unbalance", "impulse_factor")
    healthy = value("healthy_horizontal", "impulse_factor")
    assert bearing > 3 * unbalance
    assert bearing > 3 * healthy


def test_clearance_factor_is_the_most_sensitive_of_the_three():
    """It divides by the square-root mean, which suppresses large values
    hardest, so it separates impacting from steady by the widest margin."""
    bearing = features("bearing_outer_race")
    unbalance = features("unbalance")
    impulse_ratio = bearing["impulse_factor"]["value"] / unbalance["impulse_factor"]["value"]
    clearance_ratio = bearing["clearance_factor"]["value"] / unbalance["clearance_factor"]["value"]
    shape_ratio = bearing["shape_factor"]["value"] / unbalance["shape_factor"]["value"]
    assert clearance_ratio > impulse_ratio > shape_ratio


def test_burst_count_fires_only_on_impacting():
    """Steady faults raise RMS without producing samples beyond 4 sigma."""
    assert value("bearing_outer_race", "burst_count") > 50
    assert value("bearing_inner_race", "burst_count") > 5
    for steady in ("unbalance", "misalignment", "healthy_horizontal", "healthy_vertical"):
        assert value(steady, "burst_count") == 0, f"{steady} should have no bursts"


def test_burst_count_and_shock_index_say_different_things():
    """Many shallow spikes and one deep spike are different faults. A single
    number would conflate them, so count and depth are separate features."""
    one_deep = np.random.default_rng(0).normal(size=4096) * 0.01
    one_deep[2000] = 1.0
    many = np.random.default_rng(1).normal(size=4096) * 0.01
    many[::100] = 0.06

    deep = extract_time_features(one_deep.tolist(), FS_HZ)
    shallow = extract_time_features(many.tolist(), FS_HZ)

    assert deep["shock_index"]["value"] > shallow["shock_index"]["value"]
    assert shallow["burst_count"]["value"] > deep["burst_count"]["value"]


def test_the_burst_threshold_is_where_it_claims_to_be():
    """4 sigma, not 3 or 5. Gaussian noise gives about one exceedance in
    16,000 samples, so a clean channel reads near zero and an impacting one
    reads in the hundreds."""
    rng = np.random.default_rng(0)
    gaussian = (rng.normal(size=16_000) * 0.01).tolist()
    result = extract_time_features(gaussian, FS_HZ)
    assert result["burst_count"]["value"] < 10
    assert result["burst_count"]["metadata"]["threshold_sigma"] == BURST_SIGMA


def test_zero_crossing_rate_rises_with_high_frequency_content():
    """Cavitation is broadband; unbalance is a slow sine. The crossing rate
    separates them without an FFT."""
    assert value("cavitation", "zero_crossing_rate") > 10 * value("unbalance", "zero_crossing_rate")


def test_dc_offset_reports_bias_and_is_not_confused_with_vibration():
    """ch7 on the real gateway sits near -0.145 g of standing bias. A feature
    that folded that into an amplitude would grade a stationary machine as
    faulty."""
    biased = (np.sin(np.linspace(0, 100, 4096)) * 0.01 - 0.145).tolist()
    result = extract_time_features(biased, FS_HZ)
    assert result["dc_offset"]["value"] == pytest.approx(-0.145, abs=0.005)
    # the spread is the vibration, and it is unaffected by the bias
    assert result["std_dev"]["value"] == pytest.approx(0.00707, rel=0.05)


# ---------------------------------------------------- modulation index --

def test_modulation_index_is_measured_at_shaft_rate():
    """The correction this feature needed.

    First implementation used the envelope's coefficient of variation, and it
    read 1.60 for the outer-race channel against 0.75 for the inner-race one
    -- backwards, because the outer-race impulses are eight times larger and
    dominate the spread. An inner-race defect passes through the load zone
    once per revolution and modulates AT SHAFT RATE; an outer-race defect sits
    still relative to the load and does not.
    """
    inner = value("bearing_inner_race", "modulation_index")
    outer = value("bearing_outer_race", "modulation_index")
    assert inner > outer, (
        f"inner race {inner:.3f} should modulate at shaft rate more than "
        f"outer race {outer:.3f}"
    )


def test_without_a_shaft_speed_the_feature_says_it_is_not_a_modulation_depth():
    """Reporting a different quantity under the same name, silently, is how a
    rule ends up reading the wrong thing."""
    result = features("bearing_inner_race", shaft=None)
    basis = result["modulation_index"]["metadata"]["basis"]
    assert "NOT a modulation depth" in basis
    assert result["modulation_index"]["metadata"]["shaft_hz"] is None


def test_the_known_limit_is_real_and_documented():
    """On the raw signal a strong 1X sine modulates the rectified envelope by
    itself, so a healthy channel scores nearly as high as an inner-race one.
    Pinned so nobody later treats this feature as a standalone discriminator
    -- the clean measurement demodulates the resonance band first (VIK-020).
    """
    healthy = value("healthy_horizontal", "modulation_index")
    inner = value("bearing_inner_race", "modulation_index")
    assert healthy > 0.5 * inner, (
        "the documented limitation no longer holds -- if this feature now "
        "separates healthy from inner-race on its own, update the comment in "
        "time_features.py and this test"
    )


# ----------------------------------------------- lifted, not rewritten --

def test_skewness_matches_the_existing_implementation():
    """raw_analysis.py already computes it. Two copies one convention apart --
    Fisher against Pearson, population against sample sigma -- would report
    two different numbers for the same channel."""
    from app.services.raw_analysis import compute_raw_statistics

    samples, _ = generate("cavitation")
    mine = extract_time_features(samples, FS_HZ)["skewness"]["value"]
    theirs = compute_raw_statistics(samples, FS_HZ)["skewness"]
    assert mine == pytest.approx(theirs, rel=1e-9)


def test_peak_to_peak_matches_the_existing_implementation():
    from app.services.raw_analysis import compute_raw_statistics

    samples, _ = generate("looseness")
    mine = extract_time_features(samples, FS_HZ)["peak_to_peak"]["value"]
    theirs = compute_raw_statistics(samples, FS_HZ)["peak_to_peak"]
    assert mine == pytest.approx(theirs, rel=1e-9)


# ============================================================ #
#  Gaps found by mutation testing
#
#  Each of the four below is a mutation the suite above did not
#  notice: the modulation index measured at the wrong frequency,
#  crossings counted about the wrong level, the shock index off by
#  a factor of four, and the RMS windows overlapping. None changes
#  an assertion that existed; all four change what the number means.
# ============================================================ #

def test_the_modulation_index_is_measured_at_1x_and_not_some_other_order():
    """Measuring at 2X instead of 1X kept inner above outer on the harness, so
    the ordering test could not see it. The physics is specifically 1X: a
    defect passes through the load zone once per revolution. Built here as a
    signal that is modulated at shaft rate and nothing else.
    """
    fs, shaft, n = 25600.0, 25.0, 8192
    t = np.arange(n) / fs
    carrier = np.sin(2 * np.pi * 2000.0 * t)
    modulated = (1.0 + 0.5 * np.cos(2 * np.pi * shaft * t)) * carrier

    at_shaft = extract_time_features(modulated.tolist(), fs, shaft_hz=shaft)
    at_double = extract_time_features(modulated.tolist(), fs, shaft_hz=2 * shaft)
    at_half = extract_time_features(modulated.tolist(), fs, shaft_hz=shaft / 2)

    assert at_shaft["modulation_index"]["value"] > 0.3
    assert at_double["modulation_index"]["value"] < 0.05, (
        "a signal modulated only at 1X must read near zero at 2X"
    )
    assert at_half["modulation_index"]["value"] < 0.05


def test_crossings_are_counted_about_the_mean_so_a_biased_channel_still_reads():
    """ch7 on the real gateway sits about -0.145 g off zero. Counted about
    zero, a signal smaller than its own bias never crosses and the rate reads
    zero -- which would look like a dead channel on the one channel that has
    the most bias.
    """
    fs, n = 25600.0, 8192
    t = np.arange(n) / fs
    swing = 0.01 * np.sin(2 * np.pi * 200.0 * t)

    centred = extract_time_features(swing.tolist(), fs)
    biased = extract_time_features((swing - 0.145).tolist(), fs)

    assert centred["zero_crossing_rate"]["value"] == pytest.approx(400.0, rel=0.02)
    assert biased["zero_crossing_rate"]["value"] == pytest.approx(
        centred["zero_crossing_rate"]["value"], rel=0.02), (
        "the bias changed the crossing rate, so it is being counted about zero"
    )


def test_the_shock_index_is_relative_to_the_burst_threshold():
    """The scale is the point of the number: above 1.0 means at least one
    sample crossed the burst threshold. Divided by sigma instead, every
    ordinary channel reads 3 to 5 and the threshold meaning is lost.
    """
    fs = 25600.0
    rng = np.random.default_rng(0)
    quiet = (rng.normal(size=8192) * 0.01)
    quiet[100] = 6.0 * quiet.std()          # one sample past 4 sigma

    result = extract_time_features(quiet.tolist(), fs)
    centred = quiet - quiet.mean()
    sigma = float(np.sqrt(np.mean(centred ** 2)))
    expected = float(np.max(np.abs(centred))) / (BURST_SIGMA * sigma)
    assert result["shock_index"]["value"] == pytest.approx(expected, rel=1e-9)
    assert result["shock_index"]["value"] > 1.0
    assert result["burst_count"]["value"] >= 1


def test_the_two_rms_windows_never_overlap():
    """rms_change_short compares the end of the record against its start. If
    the window grows past half the record the two share samples, and at a
    0.9 fraction they share 89% -- so a record that doubles in amplitude
    halfway through reports almost no change.
    """
    import app.ai.time_features as tf

    fs, n = 25600.0, 4096
    # An oscillation whose amplitude grows tenfold, not a DC step. The first
    # version of this test used two constant levels, which is a change of
    # bias rather than of vibration -- and bias is exactly what these
    # features now remove before measuring anything.
    t = np.arange(n) / fs
    wave = np.sin(2 * np.pi * 500.0 * t)
    envelope = np.concatenate([np.full(n // 2, 0.01), np.full(n // 2, 0.10)])
    rising = wave * envelope

    honest = extract_time_features(rising.tolist(), fs)["rms_change_short"]["value"]
    assert honest == pytest.approx(9.0, rel=0.05), (
        "a tenfold rise across the record should read as a ninefold change"
    )

    original = tf.SHORT_WINDOW_FRACTION
    try:
        tf.SHORT_WINDOW_FRACTION = 0.9
        clamped = extract_time_features(rising.tolist(), fs)["rms_change_short"]["value"]
    finally:
        tf.SHORT_WINDOW_FRACTION = original

    assert clamped == pytest.approx(honest, rel=0.05), (
        "the windows overlapped and the rise was averaged away"
    )


def test_a_sensor_bias_is_not_counted_as_impacting():
    """The bug real data exposed, and the harness never could.

    Every synthetic signature is generated about zero, so raw and centred
    agree exactly and nothing here noticed that bursts were being counted on
    the uncentred signal. A real transducer has a standing bias: ch7 on the
    gateway sits at -0.145 g, which is three times four-sigma of its own
    vibration. Measured raw, all 13,888 samples exceeded the burst threshold
    -- five of the eight channels declared every sample a four-sigma impact.
    """
    fs, n = 25600.0, 13888
    rng = np.random.default_rng(7)
    vibration = rng.normal(scale=0.012, size=n)

    clean = extract_time_features(vibration.tolist(), fs)
    biased = extract_time_features((vibration - 0.145).tolist(), fs)

    assert biased["burst_count"]["value"] < 20, (
        f"{biased['burst_count']['value']:.0f} bursts out of {n} -- the bias "
        f"is being counted as impacting"
    )
    assert biased["burst_count"]["value"] == clean["burst_count"]["value"]
    assert biased["dc_offset"]["value"] == pytest.approx(-0.145, abs=0.001)


@pytest.mark.parametrize("code", [
    "impulse_factor", "shape_factor", "clearance_factor", "burst_count",
    "shock_index", "modulation_index", "rms_change_short", "rms_change_long",
    "std_dev", "skewness", "peak_to_peak", "zero_crossing_rate",
])
def test_every_feature_but_the_offset_itself_ignores_a_standing_bias(code):
    """These measure how far a machine moves about its resting position. A
    transducer's resting position is not part of that."""
    fs, n = 25600.0, 8192
    t = np.arange(n) / fs
    signal = 0.02 * np.sin(2 * np.pi * 120.0 * t) + 0.002 * np.sin(2 * np.pi * 1700.0 * t)

    clean = extract_time_features(signal.tolist(), fs, shaft_hz=25.0)[code]["value"]
    biased = extract_time_features((signal - 0.145).tolist(), fs, shaft_hz=25.0)[code]["value"]

    assert biased == pytest.approx(clean, rel=1e-6, abs=1e-9), (
        f"{code} moved from {clean:.6g} to {biased:.6g} when a constant "
        f"-0.145 g was added"
    )


def test_the_offset_itself_still_reports_the_bias():
    """The one feature that must move with it."""
    fs, n = 25600.0, 8192
    signal = 0.02 * np.sin(np.linspace(0, 400, n))
    assert extract_time_features((signal - 0.145).tolist(), fs)["dc_offset"]["value"] \
        == pytest.approx(-0.145, abs=0.001)
