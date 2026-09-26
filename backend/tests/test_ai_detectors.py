"""Two detectors that look at all the features at once — VIK-043.

The reason both exist is testable, and the two tests that establish it are
the point of this file. A machine at genuine high load is far from the
middle of its history but perfectly along the direction its history moves
in; a small change that breaks the correlation between features is close to
the middle but in a direction the history never goes. Isolation Forest sees
the first and not the second. PCA residual sees the second and not the
first.

The rest is refusals. These models need history, and history is what this
platform does not have much of -- a detector fitted to twenty captures
calls the twenty-first anomalous whatever it contains, because it has no
idea what ordinary variation is.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.ai.detectors import (
    MIN_FEATURES,
    MIN_TRAINING_SAMPLES,
    PCA_MAX_COMPONENT_FRACTION,
    isolation_forest_verdict,
    pca_residual_verdict,
    run_detectors,
)

NAMES = [f"f{i}" for i in range(12)]


def correlated_history(n=120, features=12, seed=1):
    """A machine whose features move together, which real ones do.

    One underlying driver -- load, say -- showing up across every feature at
    once, with a little independent noise on each. This is what a healthy
    pump's feature history actually looks like, and it is the structure both
    detectors exist to learn.
    """
    rng = np.random.default_rng(seed)
    driver = rng.normal(0.0, 1.0, n)
    return np.column_stack([
        driver * (1 + 0.1 * i) + rng.normal(0.0, 0.15, n)
        for i in range(features)
    ]), driver


# ------------------------------- why there are two of them -------------

def test_a_genuine_high_load_is_isolated_but_fits_the_pattern():
    """Every feature high together, in the machine's usual proportions. Far
    from the middle of the history, so the forest flags it -- but exactly
    along the direction the history moves in, so there is almost no
    residual. A single number would have had to lose one of those facts."""
    history, driver = correlated_history()
    extreme = (driver.mean() + 2.5) * np.array([1 + 0.1 * i for i in range(12)])

    forest = isolation_forest_verdict(history, extreme, NAMES)
    pca = pca_residual_verdict(history, extreme, NAMES)

    assert forest.value > 90, "far from the crowd"
    assert pca.value < 20, "but squarely on the direction the crowd occupies"


def test_a_broken_correlation_is_not_isolated_but_does_not_fit():
    """One feature moved out of step with the rest, by an amount that leaves
    it inside its own ordinary range. The opposite verdict, and the case the
    per-feature scores cannot see at all."""
    history, _ = correlated_history()
    odd = history[0].copy()
    odd[3] += 6.0

    forest = isolation_forest_verdict(history, odd, NAMES)
    pca = pca_residual_verdict(history, odd, NAMES)

    assert pca.value > 90, "in a direction the history never goes"
    assert pca.value > forest.value, (
        "this is the case PCA residual exists for, and it must be the one "
        "that reacts more strongly"
    )


def test_the_residual_names_the_feature_that_did_not_fit():
    """"This capture does not fit" is not actionable. "...and it is feature 3
    that does not fit" is."""
    history, _ = correlated_history()
    odd = history[0].copy()
    odd[3] += 6.0

    pca = pca_residual_verdict(history, odd, NAMES)
    assert pca.drivers, "the residual must decompose"
    assert pca.drivers[0][0] == "f3"
    assert pca.drivers[0][1] > 0.5, "and f3 must dominate it"
    assert "f3" in pca.reason


def test_an_ordinary_capture_scores_low_on_both():
    history, _ = correlated_history()
    ordinary = history[5]

    assert isolation_forest_verdict(history, ordinary, NAMES).value < 50
    assert pca_residual_verdict(history, ordinary, NAMES).value < 70


# ------------------------------------------------ refusals -------------

@pytest.mark.parametrize("detector",
                         [isolation_forest_verdict, pca_residual_verdict])
def test_too_little_history_refuses_rather_than_guessing(detector):
    """A model fitted to twenty captures calls the twenty-first anomalous
    whatever it contains."""
    history, _ = correlated_history(n=MIN_TRAINING_SAMPLES - 1)
    verdict = detector(history, history[0], NAMES)

    assert verdict.scored is False
    assert verdict.value is None, "never a score, and never zero"
    assert str(MIN_TRAINING_SAMPLES) in verdict.reason


@pytest.mark.parametrize("detector",
                         [isolation_forest_verdict, pca_residual_verdict])
def test_too_few_features_refuses(detector):
    """Below four there is no combination to speak of, and the per-feature
    scores already say everything there is to say."""
    history, _ = correlated_history(features=MIN_FEATURES - 1)
    names = NAMES[:MIN_FEATURES - 1]
    assert detector(history, history[0], names).scored is False


@pytest.mark.parametrize("detector",
                         [isolation_forest_verdict, pca_residual_verdict])
def test_a_history_that_never_varies_refuses(detector):
    """A column of identical values carries no information, and dividing by
    its spread is how a detector comes to report infinity."""
    flat = np.ones((60, 12))
    verdict = detector(flat, np.ones(12), NAMES)
    assert verdict.scored is False
    assert verdict.value is None


def test_a_mostly_flat_history_refuses_rather_than_scoring_on_one_column():
    """Three varying features out of twelve is still below the floor."""
    history, _ = correlated_history()
    history[:, 3:] = 1.0
    assert isolation_forest_verdict(history, history[0], NAMES).scored is False


# --------------------------------------- the model cannot cheat --------

def test_the_model_is_capped_so_it_cannot_reconstruct_anything():
    """With 46 features and 30 captures, a PCA allowed every component
    reconstructs whatever is put in front of it -- residual zero, detector
    useless, and silently so. The cap is what stops that."""
    rng = np.random.default_rng(3)
    history = rng.normal(0.0, 1.0, (40, 30))     # no structure at all
    names = [f"f{i}" for i in range(30)]

    verdict = pca_residual_verdict(history, rng.normal(0.0, 1.0, 30), names)
    assert verdict.scored is True
    assert verdict.raw > 0, (
        "an uncapped model would fit unstructured noise perfectly and "
        "report a residual of zero for every capture"
    )
    kept = int(verdict.reason.split()[0])
    assert kept <= max(1, int(min(history.shape) * PCA_MAX_COMPONENT_FRACTION))


def test_the_same_history_gives_the_same_answer_twice():
    """An anomaly score that moves when nobody changed anything is not one
    anybody can act on."""
    history, _ = correlated_history()
    first = isolation_forest_verdict(history, history[7], NAMES)
    second = isolation_forest_verdict(history, history[7], NAMES)
    assert first.value == second.value
    assert first.raw == second.raw


def test_a_small_scale_feature_can_still_be_the_one_that_is_wrong():
    """Why the features are put on the same footing before anything else.

    Band energies run to 1e-5 and crest factor to single digits. Unscaled,
    the PCA's components are set by whichever feature has the largest
    numbers, and a feature on a tiny scale contributes so little absolute
    residual that it can never appear as a driver however far out it goes --
    it is invisible, not merely quiet.

    Here the anomaly is on a feature scaled 1e-5 while another runs at 1e5.
    Standardised, it is correctly named. Unstandardised it drops out of the
    top three entirely, and the detector reports the wrong cause with
    perfect confidence.
    """
    rng = np.random.default_rng(1)
    driver = rng.normal(0.0, 1.0, 120)
    scales = np.array([1e5, 1.0, 1.0, 1e-5] + [1.0] * 8)
    history = np.column_stack([
        driver * (1 + 0.1 * i) + rng.normal(0.0, 0.15, 120) for i in range(12)
    ]) * scales

    odd = history[0].copy()
    odd[3] += 6.0 * scales[3]          # large for f3, negligible in absolute terms

    verdict = pca_residual_verdict(history, odd, NAMES)
    named = [d[0] for d in verdict.drivers[:3]]
    assert "f3" in named, (
        f"the feature that actually moved must be named; got {named}"
    )
    assert verdict.drivers[0][0] == "f3"


# ------------------------------------------------------ together -------

def test_one_detector_failing_does_not_stop_the_other():
    history, _ = correlated_history()
    verdicts = run_detectors(history, history[0], NAMES)
    assert len(verdicts) == 2
    assert {v.method for v in verdicts} == {"isolation_forest", "pca_residual"}


def test_every_verdict_explains_itself():
    """These decide maintenance priorities, so a wrong one has to be
    traceable to the reasoning that produced it."""
    history, _ = correlated_history()
    for verdict in run_detectors(history, history[0], NAMES):
        assert len(verdict.reason) > 40
    for verdict in run_detectors(history[:5], history[0], NAMES):
        assert len(verdict.reason) > 40, "a refusal must explain itself too"
