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
