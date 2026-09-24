"""What normal looks like, learned from history — VIK-025.

The ticket's acceptance: "given N healthy captures, produces stats per
sensor, channel and feature; refuses below the minimum". The refusal is the
half that matters. A baseline built from four captures is worse than no
baseline, because everything downstream then trusts it — and the roadmap
already records what a bad reference costs here: the existing "healthy
baseline" is a copy of the very file being compared against it, and 144
readings would turn green the moment somebody nominated it.

The other half is why the statistics are robust rather than mean and
standard deviation. Measured on this engine: one contaminated capture in
twenty moves the median by 0.000% and would move a mean by 504%.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from app.ai.baseline import (
    EWMA_ALPHA,
    MAD_TO_SIGMA,
    MIN_SAMPLES,
    PREFERRED_SAMPLES,
    BaselineStats,
    Observation,
    build_all,
    build_baseline,
)

START = datetime(2026, 9, 1, tzinfo=timezone.utc)


def observations(values, quality="high", hours=1):
    return [Observation(float(v), START + timedelta(hours=i * hours), quality)
            for i, v in enumerate(values)]


def clean(n=20, seed=0):
    return list(np.random.default_rng(seed).normal(0.005, 0.0005, n))


def build(values, **kw):
    return build_baseline("sensor", 0, "rms", observations(values), **kw)


# ---------------------------------------------- why robust, not average --

def test_one_bad_capture_does_not_move_the_baseline():
    """The reason for every statistic in this module.

    A baseline is built from captures nobody inspected one by one, so it
    will contain bad ones. One capture taken while somebody hammered nearby
    moves a mean by five times the machine's whole normal level. It moves
    the median by nothing.
    """
    values = clean()
    contaminated = values.copy()
    contaminated[7] = 0.5                      # one hammer blow

    honest = build(values)
    polluted = build(contaminated)

    assert polluted.median == pytest.approx(honest.median, rel=1e-9)
    assert polluted.robust_sigma == pytest.approx(honest.robust_sigma, rel=1e-9)

    # and the comparison that makes the point
    mean_shift = abs(np.mean(contaminated) - np.mean(values)) / np.mean(values)
    assert mean_shift > 1.0, "this fixture no longer demonstrates the problem"


def test_the_spread_survives_contamination_too():
    """A median with a standard deviation beside it would be half a fix: the
    spread is what a z-score divides by, so an outlier there inflates the
    denominator and hides the next real one."""
    values = clean()
    with_outliers = values + [0.4, 0.5, 0.6]

    assert build(with_outliers).robust_sigma == pytest.approx(
        build(values).robust_sigma, rel=0.25)


def test_the_spread_is_the_median_deviation_not_the_mean_deviation():
    """Taking the mean of the absolute deviations would reintroduce exactly
    the sensitivity this avoids."""
    values = clean()
    result = build(values)
    array = np.asarray(values)

    assert result.mad == pytest.approx(
        float(np.median(np.abs(array - np.median(array)))), rel=1e-9)
    assert result.robust_sigma == pytest.approx(result.mad * MAD_TO_SIGMA, rel=1e-9)


def test_robust_sigma_matches_an_ordinary_sigma_on_clean_data():
    """The scaling exists so a threshold in sigma keeps its usual meaning.
    If it did not agree on well-behaved data it would be a different unit
    wearing the same name."""
    values = list(np.random.default_rng(1).normal(0.005, 0.0005, 400))
    result = build(values)
    assert result.robust_sigma == pytest.approx(float(np.std(values)), rel=0.15)


# ------------------------------------------------------- the refusal --

def test_it_refuses_below_the_minimum_rather_than_producing_a_weak_baseline():
    """The ticket's acceptance, and the more important half of it."""
    result = build(clean(6))

    assert result.available is False
    assert result.confidence == 0.0
    assert result.sample_count == 0
    assert "6 usable captures" in result.reason
    assert "worse than none" in result.reason


def test_a_refusal_reads_as_zero_rather_than_a_plausible_number():
    """A caller that ignores `available` and reads the median anyway should
    get something visibly wrong, not something believable."""
    result = build(clean(6))
    assert result.median == 0.0
    assert result.robust_sigma == 0.0
    assert result.z_score(0.005) is None


@pytest.mark.parametrize("n", [0, 1, 2, MIN_SAMPLES - 1])
def test_too_few_is_refused_at_every_count_below_the_bar(n):
    assert build(clean(n) if n else []).available is False


def test_exactly_the_minimum_is_accepted():
    """The bar has to be reachable, or it is a permanent refusal."""
    result = build(clean(MIN_SAMPLES))
    assert result.available is True
    assert result.sample_count == MIN_SAMPLES


def test_the_minimum_can_be_raised_by_the_caller():
    """VIK-026 sets the real bar from a time window. This is the arithmetic
    floor, not the policy."""
    assert build(clean(20), min_samples=50).available is False


# ------------------------------------------- quality gates what goes in --

def test_an_invalid_capture_never_becomes_part_of_normal():
    """VIK-022 grades every capture. A clipped or dead channel is not a
    description of the machine, and letting it in is how "confidence reduced
    due to poor signal quality" gets quietly undone at the source."""
    values = clean()
    mixed = observations(values) + observations([0.9] * 5, quality="invalid")

    result = build_baseline("sensor", 0, "rms", mixed)

    assert result.sample_count == len(values)
    assert result.excluded_count == 5
    assert result.median == pytest.approx(build(values).median, rel=1e-9)


def test_low_quality_captures_are_used_and_counted():
    """On this hardware every capture is Low -- five of eight channels are
    resolution-limited. Excluding Low would mean never building a baseline
    at all, so it is admitted, and the count says so."""
    result = build_baseline("sensor", 0, "rms",
                            observations(clean(), quality="low"))
    assert result.available is True
    assert result.sample_count == 20
    assert result.excluded_count == 0


def test_a_capture_with_a_non_finite_value_is_excluded():
    result = build_baseline("sensor", 0, "rms",
                            observations(clean() + [float("nan"), float("inf")]))
    assert result.sample_count == 20
    assert result.excluded_count == 2
    assert np.isfinite(result.median)


def test_throwing_most_of_the_window_away_lowers_confidence():
    """A window where a third of the captures were unusable describes an
    installation that is not being measured reliably, however good the
    remaining numbers look."""
    good = build_baseline("sensor", 0, "rms", observations(clean(30)))
    patchy = build_baseline(
        "sensor", 0, "rms",
        observations(clean(30)) + observations([0.9] * 20, quality="invalid"))

    assert patchy.sample_count == good.sample_count
    assert patchy.confidence < good.confidence


# --------------------------------------------------------- the numbers --

def test_the_percentiles_and_median_agree_with_a_direct_calculation():
    values = clean(40)
    result = build(values)
    assert result.p50 == pytest.approx(result.median, rel=1e-9)
    assert result.p05 == pytest.approx(float(np.percentile(values, 5)), rel=1e-9)
    assert result.p95 == pytest.approx(float(np.percentile(values, 95)), rel=1e-9)
    assert result.p05 < result.p50 < result.p95


def test_the_ewma_tracks_a_drift_the_median_ignores():
    """The two are reported side by side so a slow rise is visible as the
    gap between them -- a median that chased the drift would hide it."""
    drifting = list(np.linspace(0.005, 0.010, 40))
    result = build(drifting)

    assert result.ewma > result.median, (
        "the EWMA should have followed the rise while the median sat in the "
        "middle of the window"
    )
    assert result.ewma == pytest.approx(drifting[-1], rel=0.15)


def test_the_ewma_weights_the_newest_capture_whatever_order_they_arrive_in():
    """Fed oldest-first regardless of the input order, or the weight lands
    on whichever row the query happened to return last."""
    rising = list(np.linspace(0.005, 0.010, 30))
    forwards = build_baseline("s", 0, "rms", observations(rising))
    backwards = build_baseline(
        "s", 0, "rms", list(reversed(observations(rising))))
    assert forwards.ewma == pytest.approx(backwards.ewma, rel=1e-9)


def test_the_window_records_what_it_was_built_from():
    result = build(clean(20))
    assert result.window_start == START
    assert result.window_end == START + timedelta(hours=19)
    assert result.sample_count == 20


# ----------------------------------------------------------- z-scores --

def test_a_z_score_is_in_robust_sigmas():
    result = build(clean(40))
    value = result.median + 3 * result.robust_sigma
    assert result.z_score(value) == pytest.approx(3.0, rel=1e-6)


def test_no_baseline_means_no_z_score_rather_than_zero():
    """Zero would read as "perfectly normal" for a machine nobody has a
    normal for."""
    assert build(clean(4)).z_score(0.005) is None
    assert BaselineStats("s", 0, "rms").z_score(1.0) is None


def test_a_channel_that_never_moves_at_all_is_refused():
    """Twenty captures all reading exactly the same number cannot be told
    apart from one file uploaded twenty times, and one of those two is the
    mistake this platform already made. Refusing costs little -- no z-score
    was computable either way -- and it keeps a wrong median out.
    """
    result = build([0.0015] * 20)

    assert result.available is False
    assert result.distinct_count == 1
    assert result.z_score(0.003) is None
    assert "one measurement repeated" in result.reason


# ------------------------------------------------------------ the fleet --

def test_every_channel_and_feature_gets_its_own_normal():
    """A baseline is per sensor, per channel, per feature. One number for a
    whole sensor would compare a quiet channel against a loud one."""
    keys = {(ch, code): observations(clean(20, seed=ch))
            for ch in range(3) for code in ("rms", "peak")}
    result = build_all("sensor", keys)

    assert set(result) == set(keys)
    assert all(r.available for r in result.values())
    assert result[(0, "rms")].median != result[(1, "rms")].median


def test_features_that_refuse_are_returned_rather_than_dropped():
    """A caller has to be able to say "no baseline yet, and here is why",
    which it cannot do from an absent key."""
    result = build_all("sensor", {
        (0, "rms"): observations(clean(20)),
        (0, "peak"): observations(clean(3)),
    })

    assert set(result) == {(0, "rms"), (0, "peak")}
    assert result[(0, "peak")].available is False
    assert result[(0, "peak")].reason


# ------------------------------------------------------------ the shape --

def test_confidence_rises_with_the_sample_count():
    counts = [MIN_SAMPLES, 20, PREFERRED_SAMPLES, 60]
    confidences = [build(clean(n, seed=n)).confidence for n in counts]
    assert confidences == sorted(confidences)
    assert confidences[-1] == pytest.approx(1.0)


def test_the_serialised_form_carries_the_refusal_too():
    payload = build(clean(4)).as_dict()
    assert payload["available"] is False
    assert payload["reason"]
    assert payload["sample_count"] == 0


def test_nothing_raises_on_an_empty_or_odd_history():
    for history in ([], observations([]), observations([0.0] * 20),
                    observations([-1.0] * 20), observations([1e-30] * 20)):
        result = build_baseline("s", 0, "rms", history)
        assert isinstance(result.available, bool)
        assert np.isfinite(result.median)


def test_the_ewma_weight_is_what_the_module_says_it_is():
    assert 0 < EWMA_ALPHA < 1
    values = [0.0, 1.0]
    # Not enough for a baseline, so check the arithmetic directly instead.
    expected = EWMA_ALPHA * 1.0 + (1 - EWMA_ALPHA) * 0.0
    assert expected == pytest.approx(EWMA_ALPHA)


# ------------------------------------------ gaps mutation testing found --

def test_confidence_rises_strictly_with_the_sample_count():
    """Asserting the list is merely sorted lets a constant confidence pass,
    since a flat list is sorted. The point is that more captures are worth
    more."""
    counts = [MIN_SAMPLES, 20, PREFERRED_SAMPLES]
    confidences = [build(clean(n, seed=n)).confidence for n in counts]
    for earlier, later in zip(confidences, confidences[1:]):
        assert later > earlier, (
            f"confidence did not rise between sample counts: {confidences}"
        )


def test_a_refused_baseline_offers_no_z_score_even_if_a_spread_is_present():
    """`available` and the spread are separate guards, and a test that only
    ever sees them fail together cannot tell which one is doing the work.

    This matters because a refusal is the state a caller is most likely to
    read past: the statistics look populated.
    """
    refused = BaselineStats("sensor", 0, "rms", median=0.005,
                            robust_sigma=0.0005, sample_count=4,
                            available=False)
    assert refused.robust_sigma > 0, "the spread must be real for this to test"
    assert refused.z_score(0.010) is None, (
        "a baseline nobody may use still produced a z-score"
    )

    usable = BaselineStats("sensor", 0, "rms", median=0.005,
                           robust_sigma=0.0005, available=True)
    assert usable.z_score(0.010) == pytest.approx(10.0)


def test_the_ewma_weight_is_the_declared_one():
    """A ratio test cannot tell 0.2 from 0.8 -- both follow a rise. The
    arithmetic is checked against a direct calculation instead, so the
    constant means what it says.
    """
    values = [float(v) for v in range(1, 21)]      # 20 distinct values
    result = build(values)

    expected = values[0]
    for value in values[1:]:
        expected = EWMA_ALPHA * value + (1 - EWMA_ALPHA) * expected

    assert result.ewma == pytest.approx(expected, rel=1e-12), (
        f"EWMA {result.ewma} against {expected} computed with "
        f"EWMA_ALPHA={EWMA_ALPHA}"
    )
    # and it is genuinely sensitive to the weight
    inverted = values[0]
    for value in values[1:]:
        inverted = (1 - EWMA_ALPHA) * value + EWMA_ALPHA * inverted
    assert abs(expected - inverted) > 1.0, "this fixture cannot tell them apart"


def test_the_window_is_ordered_by_time_not_by_arrival():
    """Captures do not necessarily reach this function in order -- a query
    without an ORDER BY returns whatever the planner chose. Taking the first
    and last as they arrive then reports a window that never happened, and
    the EWMA weights the wrong capture.
    """
    values = clean(20)
    in_order = observations(values)
    shuffled = list(in_order)
    shuffled.reverse()

    forwards = build_baseline("sensor", 0, "rms", in_order)
    backwards = build_baseline("sensor", 0, "rms", shuffled)

    assert backwards.window_start == forwards.window_start == START
    assert backwards.window_end == forwards.window_end
    assert backwards.window_start < backwards.window_end
    assert backwards.ewma == pytest.approx(forwards.ewma, rel=1e-9)


# ------------------------------- one file uploaded many times is one sample --

def test_the_same_capture_repeated_is_not_a_history():
    """The failure this platform already has on disk.

    Nine of the stored captures are one synthetic test file uploaded nine
    times: nine rows, one distinct value, an RMS of 0.29962 against a real
    machine level of 0.0122. Counted as nine independent samples they look
    like evidence, and the roadmap records the same shape of mistake --
    the existing "healthy baseline" is a copy of the very file being
    compared against it.
    """
    result = build([0.29962] * 20)

    assert result.available is False
    assert result.distinct_count == 1
    assert "one measurement repeated" in result.reason
    assert "not a history" in result.reason


def test_two_distinct_values_are_still_not_a_spread():
    """With two values there is no way to tell a range from an outlier."""
    assert build([0.005] * 10 + [0.006] * 10).available is False


def test_a_quantised_channel_with_real_repeats_still_gets_a_baseline():
    """Genuine repeats are expected. A channel spanning a couple of converter
    counts returns the same reading often, and that is a real measurement
    landing on the same step -- refusing it would lose the baseline for the
    channels that most need one."""
    step = 5 / 32768 / 0.100
    values = [step * n for n in (1, 1, 1, 2, 2, 2, 2, 1, 2, 3, 2, 1, 2, 2, 1, 3)]
    result = build(values)

    assert result.available is True
    assert result.distinct_count == 3
    assert result.sample_count == len(values)


def test_the_distinct_count_is_reported_even_when_the_baseline_is_fine():
    """A reader should be able to see how much of the window was repetition
    without having to re-derive it."""
    result = build(clean(20))
    assert result.distinct_count == 20
    assert result.as_dict()["distinct_count"] == 20


def test_a_mostly_repeated_window_has_no_z_score():
    """Eleven of twenty captures identical puts the median absolute
    deviation at zero even though the values are not all the same. Dividing
    by it would give infinity, which grades as critical."""
    values = [0.0015] * 11 + [0.0030, 0.0045, 0.0015, 0.0030, 0.0015,
                              0.0045, 0.0030, 0.0015, 0.0030]
    result = build(values)

    assert result.available is True
    assert result.robust_sigma == 0.0
    assert result.z_score(0.006) is None
    assert "no usable spread" in result.reason


def test_an_unassessed_capture_is_not_treated_as_a_good_one():
    """'unknown' is admissible but it is not 'high'. The nine synthetic
    uploads predate the quality engine and have no samples left to assess,
    and defaulting them to the best grade is how they were admitted as
    exemplary."""
    from app.ai.baseline import ACCEPTABLE_QUALITY, EXCLUDED_QUALITY

    assert "unknown" in ACCEPTABLE_QUALITY
    assert "unknown" not in EXCLUDED_QUALITY

    result = build_baseline("sensor", 0, "rms",
                            observations(clean(20), quality="unknown"))
    assert result.available is True


# ----------------------------------- a window holding two different things --

def test_a_foreign_population_in_the_window_is_named():
    """The median and MAD shrug off a contaminated minority -- that is what
    they are for -- but the percentiles cannot, because the percentiles ARE
    the distribution.

    Measured on this platform's own history: nine synthetic captures reading
    0.29962 against a real machine level of 0.01225 leave the median exactly
    where it should be and put p95 sixty-five sigma out.
    """
    real = list(np.random.default_rng(0).normal(0.0122, 0.0044, 124))
    contaminated = real + [0.29962] * 9

    result = build(contaminated)

    assert result.available is True, "the median is still usable"
    assert result.median == pytest.approx(0.0122, abs=0.002)
    assert result.mixed_population is True
    assert "second population" in result.reason
    assert "sigma out" in result.reason


def test_the_same_data_without_the_intruders_is_not_flagged():
    """The check has to discriminate, not just fire. On the real history this
    is the difference between the full window and a fourteen-day one: p95
    0.29962 against 0.01521."""
    real = list(np.random.default_rng(0).normal(0.0122, 0.0044, 124))
    result = build(real)

    assert result.mixed_population is False
    assert result.p95 < result.median + 6 * result.robust_sigma
    assert result.confidence > 0.9


def test_contamination_halves_the_confidence_without_hiding_the_baseline():
    """The robust statistics survived, so the baseline is still offered --
    but the window is not what it claims to be, and a caller weighing it
    should see that."""
    real = list(np.random.default_rng(0).normal(0.0122, 0.0044, 124))
    honest = build(real)
    mixed = build(real + [0.29962] * 9)

    assert mixed.available is True
    assert mixed.confidence == pytest.approx(honest.confidence * 0.5, abs=0.06)
    assert mixed.confidence < honest.confidence


def test_an_ordinary_skew_is_not_called_contamination():
    """Plenty of vibration features are skewed -- kurtosis and the burst
    count both are. Six sigma is far enough out to leave them alone."""
    skewed = list(np.random.default_rng(2).gamma(shape=3.0, scale=0.002, size=200))
    result = build(skewed)
    assert result.mixed_population is False, (
        f"a gamma-distributed feature was called contaminated: p95 "
        f"{result.p95:.5f} against median {result.median:.5f} and sigma "
        f"{result.robust_sigma:.5f}"
    )


def test_the_flag_is_carried_into_the_serialised_form():
    real = list(np.random.default_rng(0).normal(0.0122, 0.0044, 124))
    payload = build(real + [0.29962] * 9).as_dict()
    assert payload["mixed_population"] is True
    assert payload["available"] is True


def test_a_feature_with_no_spread_is_not_also_called_contaminated():
    """Dividing by a zero spread to measure the reach of p95 would give
    infinity, which is not a population problem."""
    values = [0.0015] * 11 + [0.0030, 0.0045, 0.0015, 0.0030, 0.0015,
                              0.0045, 0.0030, 0.0015, 0.0030]
    result = build(values)
    assert result.robust_sigma == 0.0
    assert result.mixed_population is False


# --------------------------- a baseline belongs to one acquisition shape --

from app.ai.baseline import AcquisitionShape  # noqa: E402

OLD_SHAPE = AcquisitionShape(50_000.0, 13_888)      # 0.278 s, what was stored
NEW_SHAPE = AcquisitionShape(25_000.0, 20_000)      # 0.800 s, what the gateway sends now


def shaped(values, shape, start_hour=0):
    return [Observation(float(v), START + timedelta(hours=start_hour + i),
                        "high", shape)
            for i, v in enumerate(values)]


def test_a_window_spanning_a_settings_change_keeps_only_the_newer_shape():
    """Half the features move by a quarter or more when the sample rate or
    record length changes -- the zero-crossing rate and spectral centroid
    both nearly halve. A baseline learned across both would be half one
    configuration and half another, and would then find every capture
    anomalous."""
    history = (shaped(clean(20, seed=1), OLD_SHAPE)
               + shaped(clean(20, seed=2), NEW_SHAPE, start_hour=100))

    result = build_baseline("sensor", 0, "zero_crossing_rate", history)

    assert result.available is True
    assert result.sample_count == 20
    assert result.other_shape_count == 20
    assert result.shape == NEW_SHAPE
    assert result.confidence_note and "different acquisition shape" in result.confidence_note


def test_too_few_captures_at_the_new_shape_refuses_rather_than_reaching_back():
    """After a settings change there is a gap with no usable baseline. That
    is the honest state, and borrowing the old shape's numbers to fill it is
    exactly the mistake."""
    history = (shaped(clean(40, seed=1), OLD_SHAPE)
               + shaped(clean(3, seed=2), NEW_SHAPE, start_hour=100))

    result = build_baseline("sensor", 0, "spectral_centroid", history)

    assert result.available is False
    assert result.other_shape_count == 40
    assert "different acquisition shape" in result.reason
    assert "every capture anomalous" in result.reason


def test_a_capture_of_a_different_shape_is_not_compared():
    """The guard that stops the false alarm reaching a screen."""
    result = build_baseline("sensor", 0, "zero_crossing_rate",
                            shaped(clean(20), NEW_SHAPE))

    assert result.comparable_with(NEW_SHAPE) is True
    assert result.comparable_with(OLD_SHAPE) is False
    assert result.comparable_with(AcquisitionShape(25_000.0, 13_888)) is False
    assert result.comparable_with(AcquisitionShape(50_000.0, 20_000)) is False


def test_an_unknown_shape_compares_against_nothing():
    """Not because it is probably different, but because it cannot be shown
    to be the same -- and a comparison that might be measuring a settings
    change is not one to act on. The rows written before this existed have
    no shape recorded."""
    unknown = build_baseline("sensor", 0, "rms", observations(clean(20)))

    assert unknown.shape.known is False
    assert unknown.comparable_with(NEW_SHAPE) is False
    assert unknown.comparable_with(AcquisitionShape()) is False


def test_a_single_shape_window_is_untouched():
    """The scoping must not cost anything when nothing changed."""
    plain = build_baseline("sensor", 0, "rms", observations(clean(20)))
    shaped_only = build_baseline("sensor", 0, "rms", shaped(clean(20), NEW_SHAPE))

    assert shaped_only.other_shape_count == 0
    assert shaped_only.confidence_note is None
    assert shaped_only.median == pytest.approx(plain.median, rel=1e-9)
    assert shaped_only.confidence == pytest.approx(plain.confidence)


def test_the_shape_describes_itself_in_words_a_person_can_check():
    assert "0.8 s at 25 kSPS" in NEW_SHAPE.describe()
    assert "20000 samples" in NEW_SHAPE.describe()
    assert NEW_SHAPE.duration_s == pytest.approx(0.8)
    assert OLD_SHAPE.duration_s == pytest.approx(0.27776, rel=1e-3)
    assert "unrecorded" in AcquisitionShape().describe()


def test_the_shape_is_carried_into_the_serialised_form():
    payload = build_baseline("sensor", 0, "rms", shaped(clean(20), NEW_SHAPE)).as_dict()
    assert payload["acquisition_sample_rate_hz"] == 25_000.0
    assert payload["acquisition_sample_count"] == 20_000
