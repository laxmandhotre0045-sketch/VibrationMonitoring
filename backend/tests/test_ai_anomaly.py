"""How unusual a reading is, from 0 to 100 — VIK-042.

The ticket's acceptance is one sentence: "A feature with no baseline scores
unknown, never normal -- that distinction must survive." Most of this file
defends that sentence, because zero is the tempting answer and it is the
worst one available: it makes an unmonitored machine score better than a
monitored healthy one, and sends it to the bottom of every priority list
precisely because nobody has ever looked at it.

The rest is about the map from sigma to score. It has to mean the same
thing on every feature of every machine, or two machines cannot be compared
and the whole ranking is noise.
"""

from __future__ import annotations

import pytest

from app.ai.anomaly import (
    BANDS,
    SIGMA_ANCHORS,
    Score,
    band_for,
    score_capture,
    score_feature,
    score_from_sigma,
    worst,
)

NORMAL = {"median": 10.0, "robust_sigma": 2.0, "confidence": 1.0,
          "baseline_version": 7}


# ------------------------------- unknown is never normal ---------------

def test_a_feature_with_no_baseline_is_unscored_not_zero():
    """The ticket. Zero says "perfectly ordinary" about a reading nothing
    has ever been compared to."""
    result = score_feature("rms", 0, 12.0, None)
    assert result.scored is False
    assert result.value is None
    assert result.band is None
    assert "not a reading that looks ordinary" in result.reason


def test_a_feature_that_was_not_computed_is_unscored():
    result = score_feature("rms", 0, None, NORMAL)
    assert result.scored is False
    assert result.value is None


def test_an_informational_feature_is_recorded_but_not_scored():
    """Eight features describe the signal rather than the machine's health.
    A distance from normal on one of them is not evidence of anything, and
    scoring it would put noise into the ranking."""
    result = score_feature("dc_offset", 0, 99.0, NORMAL, informational=True)
    assert result.scored is False
    assert result.reading == 99.0, "the reading is still kept"
    assert "rather than the machine" in result.reason


def test_a_baseline_with_no_spread_cannot_score():
    """Every capture behind it read the same value, so every new reading is
    either exactly normal or infinitely abnormal. Neither is useful."""
    flat = {"median": 10.0, "robust_sigma": 0.0, "confidence": 1.0}
    result = score_feature("rms", 0, 10.5, flat)
    assert result.scored is False
    assert "no spread" in result.reason


def test_an_incomplete_baseline_cannot_score():
    assert score_feature("rms", 0, 12.0, {"median": 10.0}).scored is False
    assert score_feature("rms", 0, 12.0, {"robust_sigma": 2.0}).scored is False


def test_worst_of_nothing_is_none_not_a_zero():
    """A capture where nothing could be scored has no worst feature.
    Inventing one at the bottom of the range would report it as the
    healthiest thing on the machine."""
    unscored = [score_feature("rms", 0, 12.0, None),
                score_feature("peak", 0, 3.0, None)]
    assert worst(unscored) is None


# ------------------------------------ the map from sigma to score ------

@pytest.mark.parametrize("sigma,expected", [
    (0.0, 0.0), (1.0, 20.0), (2.0, 40.0), (3.0, 61.0),
    (4.5, 76.0), (6.0, 91.0), (9.0, 100.0),
])
def test_the_anchors_land_where_the_requirement_puts_them(sigma, expected):
    """One sigma is the top of normal; three is the bottom of abnormal,
    which is where conventional practice puts it; six is where the
    baseline's own contamination check draws its line."""
    assert score_from_sigma(sigma) == pytest.approx(expected, abs=0.1)


def test_the_score_never_leaves_the_range():
    for sigma in (0.0, 1.0, 5.0, 9.0, 50.0, 1000.0):
        assert 0.0 <= score_from_sigma(sigma) <= 100.0


def test_more_unusual_always_scores_higher():
    """Not merely at the anchors. A map that dipped between them would make
    a worse reading rank lower than a better one."""
    previous = -1.0
    sigma = 0.0
    while sigma <= 12.0:
        value = score_from_sigma(sigma)
        assert value >= previous, f"score fell at {sigma} sigma"
        previous = value
        sigma += 0.1


def test_distance_is_what_counts_not_direction():
    """A bearing band that collapses is as interesting as one that climbs."""
    assert score_from_sigma(3.0) == score_from_sigma(-3.0)


@pytest.mark.parametrize("score,band", [
    (0, "normal"), (20, "normal"), (21, "slight"), (40, "slight"),
    (41, "watch"), (60, "watch"), (61, "abnormal"), (75, "abnormal"),
    (76, "high"), (90, "high"), (91, "critical"), (100, "critical"),
])
def test_the_bands_are_the_ones_the_requirement_names(score, band):
    assert band_for(score) == band


def test_every_band_is_reachable():
    """A band nothing can land in is a band that does not exist."""
    reachable = {band_for(score_from_sigma(s / 10)) for s in range(0, 150)}
    assert reachable == {name for _, name in BANDS}


# ----------------------------------- score and confidence are apart ----

def test_the_reading_is_scored_by_how_far_out_it_is():
    result = score_feature("rms", 2, 16.0, NORMAL)     # 3 sigma above
    assert result.scored is True
    assert result.z == pytest.approx(3.0)
    assert result.value == pytest.approx(61.0, abs=0.1)
    assert result.band == "abnormal"


def test_direction_survives_in_the_z_score():
    above = score_feature("rms", 0, 16.0, NORMAL)
    below = score_feature("rms", 0, 4.0, NORMAL)
    assert above.z > 0 and below.z < 0
    assert above.value == below.value, "distance decides the score"
    assert "above" in above.reason and "below" in below.reason


def test_a_poor_capture_lowers_the_confidence_not_the_score():
    """A clipped capture that reads eight sigma out really is eight sigma
    out, and pretending otherwise would hide a genuine clipping fault. What
    changes is how much anyone should act on it."""
    good = score_feature("rms", 0, 16.0, NORMAL, quality_factor=1.0)
    poor = score_feature("rms", 0, 16.0, NORMAL, quality_factor=0.4)

    assert poor.value == good.value
    assert poor.confidence < good.confidence
    assert poor.confidence == pytest.approx(0.4)


def test_a_thin_baseline_lowers_the_confidence_too():
    """A 90 from a baseline of thirteen captures and a 45 from one of two
    hundred are not the same finding."""
    thin = dict(NORMAL, confidence=0.5)
    assert score_feature("rms", 0, 16.0, thin).confidence == pytest.approx(0.5)


def test_both_reasons_to_doubt_compound():
    thin = dict(NORMAL, confidence=0.5)
    result = score_feature("rms", 0, 16.0, thin, quality_factor=0.4)
    assert result.confidence == pytest.approx(0.2)


def test_the_baseline_it_was_judged_against_travels_with_the_score():
    """A score is a function of a normal, and baselines change. Without
    this, a finding that said 84 quietly becomes 31."""
    scoped = dict(NORMAL, mode_id="mode-abc")
    result = score_feature("rms", 0, 16.0, scoped)
    assert result.baseline_version == 7
    assert result.mode_id == "mode-abc"
    assert result.contributions["robust_z"]["z"] == pytest.approx(3.0)


def test_a_mixed_population_baseline_says_so_in_the_reason():
    mixed = dict(NORMAL, mixed_population=True)
    assert "more than one" in score_feature("rms", 0, 16.0, mixed).reason


# ------------------------------------------- a whole capture -----------

def test_a_capture_scores_every_feature_it_can_and_says_what_it_could_not():
    features = {(0, "rms"): 16.0, (0, "peak"): 12.0, (1, "rms"): 10.0}
    baselines = {(0, "rms"): NORMAL, (1, "rms"): NORMAL}

    scores = score_capture(features, baselines,
                           quality_by_channel={0: 1.0, 1: 0.5})

    by_key = {(s.channel, s.feature_code): s for s in scores}
    assert by_key[(0, "rms")].scored is True
    assert by_key[(0, "peak")].scored is False, "no baseline for peak"
    assert by_key[(1, "rms")].confidence == pytest.approx(0.5)

    top = worst(scores)
    assert top is not None
    assert (top.channel, top.feature_code) == (0, "rms")


def test_the_worst_is_the_highest_score_not_the_lowest_confidence():
    """Ranking is by how unusual, not by how sure. Confidence is reported
    beside the rank so somebody can discount it themselves."""
    scores = [
        Score("a", 0, value=90.0, scored=True, confidence=0.2),
        Score("b", 0, value=50.0, scored=True, confidence=1.0),
    ]
    assert worst(scores).feature_code == "a"
