"""When a score becomes an alarm — VIK-044 and VIK-046.

Two tickets, one decision. VIK-044 says a single odd reading must not ring;
VIK-046 says the four sensitivity profiles must actually change behaviour.
They meet in the same function, because what a profile mostly changes is how
long it waits.

The arithmetic behind VIK-044 is worth keeping in view while reading this
file. This pump produces a capture every two minutes and scores 368
features on each. At three sigma, chance alone puts about one reading in
370 past the line -- roughly one feature per capture, seven hundred a day,
every one of them a healthy machine behaving normally.
"""

from __future__ import annotations

import pytest

from app.ai.alarm import (
    BALANCED,
    CONSERVATIVE,
    DEFAULT_PROFILE,
    EARLY_WARNING,
    EXPERT,
    EXPERT_BOUNDS,
    PRESETS,
    PROFILES,
    consecutive_run,
    evaluate,
    evaluate_capture,
    resolve,
)

SUSTAINED = [95.0, 93.0, 91.0, 90.0]      # newest first, four past the line
SPIKE = [95.0, 12.0, 11.0, 13.0]          # one high capture, then normal


def verdict(scores, profile=BALANCED, confidence=0.9, **kw):
    return evaluate(2, "rms", scores, confidence=confidence,
                    band="critical", sensitivity=resolve(profile, kw or None))


# ------------------------------- one reading is not evidence -----------

def test_a_single_high_reading_does_not_ring():
    """The ticket. At this threshold one feature per capture goes past the
    line by chance, and alarming on those is arithmetic, not sensitivity."""
    result = verdict(SPIKE)
    assert result.alarming is False
    assert result.held_back == "not_persistent"
    assert result.run_length == 1
    assert "arithmetic rather than evidence" in result.reason


def test_a_sustained_reading_rings():
    result = verdict(SUSTAINED)
    assert result.alarming is True
    assert result.held_back is None
    assert result.run_length >= result.required


def test_the_run_has_to_be_consecutive():
    """A feature that alarms, recovers and alarms again is doing something
    different from one steadily getting worse, and the difference matters to
    whoever is deciding whether to stop the machine."""
    broken = [95.0, 93.0, 10.0, 92.0, 91.0]      # three highs, not in a row
    result = verdict(broken)
    assert result.run_length == 2
    assert result.alarming is False


def test_a_gap_in_the_evidence_ends_the_run():
    """An unscored capture is not a continuation. Skipping over it would let
    a fault seen twice, months apart, ring as though it had been steady."""
    assert consecutive_run([95.0, 93.0, None, 92.0, 91.0], 61.0) == 2
    assert consecutive_run([None, 95.0, 93.0, 91.0], 61.0) == 0


def test_a_feature_that_could_not_be_scored_does_not_ring():
    """And is not the same as one that came back normal."""
    result = verdict([None, 95.0, 93.0])
    assert result.alarming is False
    assert result.score is None
    assert "Not the same as a reading that came back normal" in result.reason


def test_a_reading_below_the_line_is_not_held_back():
    """Held back means "past the line but not acted on". A quiet feature is
    not being suppressed and must not be counted as though it were."""
    result = verdict([10.0, 11.0, 12.0])
    assert result.alarming is False
    assert result.held_back is None
    assert result.run_length == 0


# ------------------------------- the profiles change behaviour ---------

def test_the_same_evidence_gives_different_answers_per_profile():
    """VIK-046. Three captures past the line: Conservative wants four and
    stays quiet, Balanced wants three and rings, Early Warning wanted two
    and has been ringing since the capture before."""
    three = [95.0, 93.0, 91.0]
    assert verdict(three, CONSERVATIVE).alarming is False
    assert verdict(three, BALANCED).alarming is True
    assert verdict(three, EARLY_WARNING).alarming is True


def test_conservative_waits_longer_and_demands_more_than_early_warning():
    """The trade a person is choosing between, stated as an ordering."""
    low, high = PRESETS[EARLY_WARNING], PRESETS[CONSERVATIVE]
    assert high.persistence > low.persistence
    assert high.score_threshold >= low.score_threshold
    assert high.min_confidence > low.min_confidence
    assert high.baseline_days > low.baseline_days


def test_no_profile_ever_rings_on_a_single_capture():
    """Even Early Warning waits for two. One reading is not evidence at any
    sensitivity, and a profile that ignored that would make the platform
    noise whatever else it got right."""
    for profile in PROFILES:
        assert resolve(profile).persistence >= 2


def test_an_unconfigured_machine_gets_the_recommended_default():
    """Not the most eager setting. Defaulting to Early Warning would make
    every unconfigured machine the noisiest thing on the plant."""
    assert resolve(None).profile == DEFAULT_PROFILE
    assert resolve("").profile == DEFAULT_PROFILE


def test_an_unknown_profile_falls_back_rather_than_raising():
    """Read on every capture. A typo in a settings row must not stop a
    machine being monitored -- and must not silently make it the most
    sensitive one either."""
    fallback = resolve("agressive")           # sic
    assert fallback.profile == DEFAULT_PROFILE


# ------------------------------------------------- expert mode ---------

def test_expert_mode_uses_the_numbers_it_is_given():
    settings = resolve(EXPERT, {"score_threshold": 45, "persistence": 6,
                                "min_confidence": 0.3})
    assert settings.profile == EXPERT
    assert settings.score_threshold == 45
    assert settings.persistence == 6
    assert settings.min_confidence == pytest.approx(0.3)


def test_expert_mode_cannot_be_configured_into_silence_or_into_noise():
    """Both extremes look like a working setup from the settings page: a
    threshold of 100 says nothing ever, a persistence of 1 says everything
    always."""
    silent = resolve(EXPERT, {"score_threshold": 100.0, "persistence": 500})
    assert silent.score_threshold <= EXPERT_BOUNDS["score_threshold"][1]
    assert silent.persistence <= EXPERT_BOUNDS["persistence"][1]

    noisy = resolve(EXPERT, {"score_threshold": 0.0, "persistence": 1})
    assert noisy.score_threshold >= EXPERT_BOUNDS["score_threshold"][0]
    assert noisy.persistence >= 2, "one capture is never enough"


def test_expert_mode_ignores_what_it_cannot_use():
    """A nonsense value falls back to the Balanced number rather than
    raising or being taken literally."""
    settings = resolve(EXPERT, {"score_threshold": "high",
                                "persistence": None,
                                "nonsense_key": 5})
    assert settings.score_threshold == PRESETS[BALANCED].score_threshold
    assert settings.persistence == PRESETS[BALANCED].persistence


# --------------------------------- confidence gates the alarm ----------

def test_a_sustained_finding_on_a_weak_baseline_does_not_ring():
    """VIK-042 keeps how unusual a reading is apart from how much the
    comparison is worth. This is where the second number finally decides
    something."""
    result = verdict(SUSTAINED, confidence=0.2)
    assert result.alarming is False
    assert result.held_back == "low_confidence"
    assert "what is in doubt is the normal" in result.reason


def test_the_score_is_still_reported_when_the_alarm_is_held_back():
    """The reading is real. What is in doubt is the yardstick."""
    result = verdict(SUSTAINED, confidence=0.2)
    assert result.score == 95.0
    assert "95" in result.reason


def test_early_warning_accepts_a_thinner_baseline_than_conservative():
    """Being told early about a machine that matters is worth being wrong
    more often -- and that is a choice, made per machine."""
    assert verdict(SUSTAINED, EARLY_WARNING, confidence=0.45).alarming is True
    assert verdict(SUSTAINED, CONSERVATIVE, confidence=0.45).alarming is False


def test_an_unknown_confidence_does_not_block_the_alarm():
    """None is "nobody measured it", not "it is bad". Blocking on it would
    silence a platform whose confidence column had not been populated."""
    assert verdict(SUSTAINED, confidence=None).alarming is True


# ----------------------------------------------- a whole capture -------

def test_a_capture_ranks_what_is_ringing_first():
    histories = {
        (0, "rms"): [95.0, 93.0, 91.0],
        (0, "peak"): [99.0, 10.0, 10.0],        # one spike, louder
        (1, "kurtosis"): [10.0, 10.0, 10.0],
    }
    current = {
        (0, "rms"): {"confidence": 0.9, "band": "critical"},
        (0, "peak"): {"confidence": 0.9, "band": "critical"},
        (1, "kurtosis"): {"confidence": 0.9, "band": "normal"},
    }
    verdicts = evaluate_capture(histories, current, resolve(BALANCED))

    assert verdicts[0].feature_code == "rms", (
        "the sustained finding outranks the louder single spike"
    )
    assert verdicts[0].alarming is True
    assert not any(v.alarming for v in verdicts[1:])


def test_every_verdict_explains_itself():
    """An alarm sends somebody to a machine, and a silence keeps them away.
    Both need to be defensible."""
    for scores, conf in ((SUSTAINED, 0.9), (SPIKE, 0.9),
                         (SUSTAINED, 0.1), ([10.0], 0.9)):
        assert len(verdict(scores, confidence=conf).reason) > 40
