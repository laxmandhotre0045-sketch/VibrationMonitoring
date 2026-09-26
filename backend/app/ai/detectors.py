"""Two detectors that look at all the features at once — VIK-043.

VIK-042 scores each feature against its own normal, one at a time. That
catches a feature going somewhere it has never been, and misses the thing
that actually precedes most mechanical failures: every feature staying
inside its own range while the *combination* of them stops making sense.

A pump whose 1x amplitude rises while its bearing bands fall is doing
something it has never done before. Neither number is remarkable on its
own; both sit comfortably within one sigma. Only a detector that sees them
together can say so.

**Isolation Forest** asks how few random splits it takes to cut one capture
away from the rest. A point in the middle of the crowd needs many; a point
out on its own needs few. It makes no assumption about the shape of the
data, which matters here because vibration features are not normally
distributed and several are strictly positive with a long tail.

**PCA residual** asks a different question, and the difference is the reason
both are here. It learns the handful of directions the machine's history
actually moves in -- on a healthy pump most of the variation is one or two
underlying things, load and temperature, showing up across forty features
at once -- and then measures how much of a new capture does not fit in
those directions. A capture can sit inside every individual range and still
be mostly residual, which is precisely the case the per-feature scores
cannot see.

Isolation Forest finds points far from the crowd. PCA residual finds points
that are close to the crowd but in a direction the crowd does not occupy.
Neither subsumes the other, and averaging them into one number would lose
which of those two things happened.

**Everything here refuses rather than guesses.** A model needs history, and
history is exactly what this platform does not have much of. A detector
trained on twenty captures will call the twenty-first anomalous whatever it
looks like, because it has no idea what ordinary variation is. So there is
a floor, and below it the answer is "not enough history", which travels to
the caller as unscored -- never as normal, for the same reason VIK-042
refuses to score a feature with no baseline.

**The training window is the baseline's window.** These learn from the same
captures the baseline was built from, at the same acquisition shape,
converter setting and operating mode. Anything else would have the two
halves of the platform disagreeing about what "normal" refers to.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

import numpy as np

logger = logging.getLogger(__name__)

#: Captures needed before either detector is offered at all.
#:
#: Higher than the baseline's floor of 12, and deliberately. A median needs
#: enough samples to be stable; a model that learns the *shape* of a
#: multi-dimensional cloud needs enough to have seen that shape. Thirty is
#: where the per-feature statistics stop being noisy (VIK-025's
#: PREFERRED_SAMPLES), and a model built on less than the statistics need is
#: a model pretending to know more than they do.
MIN_TRAINING_SAMPLES = 30

#: Features needed before looking at them jointly means anything. Below
#: this there is no "combination" to speak of and the per-feature scores
#: already say everything there is to say.
MIN_FEATURES = 4

#: How much of the history's variation the retained components must explain.
#:
#: The point of the residual is that it is the part the machine does not
#: normally do. Keep too few components and ordinary behaviour lands in the
#: residual, so everything looks anomalous; keep too many and the model
#: reconstructs anything, so nothing does. 90% leaves a residual that is
#: genuinely the leftovers on this platform's data, where the first two
#: components of a healthy pump's features carry most of it.
PCA_VARIANCE_TARGET = 0.90

#: Never keep more than this fraction of the available components, however
#: the variance falls. With 46 features and 30 captures a model allowed all
#: of them reconstructs every capture perfectly, residual zero, detector
#: useless -- and silently so.
PCA_MAX_COMPONENT_FRACTION = 0.5

#: Trees in the forest. The default, and enough that the path lengths are
#: stable between runs; the cost is milliseconds at this data size.
FOREST_TREES = 100

#: A fixed seed, so the same history produces the same model. An anomaly
#: score that changes when nobody changed anything is not a score anyone can
#: act on, and "it was different yesterday" is not something a maintenance
#: engineer should ever have to hear.
RANDOM_SEED = 20260926


@dataclass
class DetectorVerdict:
    """What one detector made of one capture."""
    method: str
    scored: bool = False
    #: 0-100, on the same scale as VIK-042 so they can sit side by side.
    value: Optional[float] = None
    #: The detector's own raw output, kept because the 0-100 mapping is a
    #: presentation choice and the raw number is the evidence.
    raw: Optional[float] = None
    reason: str = ""
    #: Features that contributed most, worst first. Empty for Isolation
    #: Forest, which does not decompose.
    drivers: list[tuple[str, float]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"method": self.method, "scored": self.scored,
                "score": self.value, "raw": self.raw, "reason": self.reason,
                "drivers": [{"feature": f, "share": round(s, 3)}
                            for f, s in self.drivers]}


def _unscored(method: str, reason: str) -> DetectorVerdict:
    return DetectorVerdict(method=method, scored=False, value=None,
                           reason=reason)


def _robust_standardise(
    history: np.ndarray, reading: np.ndarray
) -> Optional[tuple[np.ndarray, np.ndarray]]:
    """Put every feature on the same footing, robustly.

    Band energies run to 1e-5 and crest factor to single digits, and the
    consequence is sharper than "the big feature dominates". A feature on a
    tiny scale contributes so little *absolute* residual that it can never
    appear as a driver however far out it goes -- it is invisible, not
    merely quiet. Measured on a history where one feature runs at 1e5 and
    another at 1e-5, putting the anomaly on the small one: standardised, it
    is correctly named; unstandardised, it drops out of the top three and
    the detector reports the wrong cause with no sign that it has.

    Median and MAD rather than mean and standard deviation, for the reason
    the baseline uses them: the training window is captures nobody
    inspected, and one bad one must not set the scale for the rest.

    A feature that never varies is dropped rather than kept as a column of
    zeros: it carries no information, and dividing by its spread is how a
    detector comes to report infinity.
    """
    median = np.median(history, axis=0)
    mad = np.median(np.abs(history - median), axis=0) * 1.4826
    usable = mad > 0
    if usable.sum() < MIN_FEATURES:
        return None
    return ((history[:, usable] - median[usable]) / mad[usable],
            (reading[usable] - median[usable]) / mad[usable])


def _usable_columns(history: np.ndarray) -> np.ndarray:
    median = np.median(history, axis=0)
    mad = np.median(np.abs(history - median), axis=0) * 1.4826
    return mad > 0


def isolation_forest_verdict(
    history: Sequence[Sequence[float]],
    reading: Sequence[float],
    feature_names: Sequence[str],
) -> DetectorVerdict:
    """How easily this capture can be cut away from the machine's history.

    The score is the forest's own, mapped onto 0-100 by where the capture
    falls against the *training set's* own scores rather than against an
    absolute threshold. That matters: a forest's raw score depends on the
    data it was fitted to, so the same number means different things on
    different machines. Ranking against the history it learned from is what
    makes 80 mean the same thing everywhere -- "more isolated than 80% of
    what this machine normally does".
    """
    method = "isolation_forest"
    X = np.asarray(history, dtype=float)
    x = np.asarray(reading, dtype=float)

    if X.ndim != 2 or X.shape[0] < MIN_TRAINING_SAMPLES:
        return _unscored(method, (
            f"{0 if X.ndim != 2 else X.shape[0]} captures of history, and "
            f"{MIN_TRAINING_SAMPLES} are needed. A forest trained on less "
            f"has not seen enough to know what ordinary variation looks "
            f"like, and would call the next capture anomalous whatever it "
            f"contained."))
    # Reached again by `_robust_standardise`, which refuses on the same
    # count after dropping the features that never vary -- so this is an
    # early exit with a better message, not the guard. Said plainly because
    # a line that looks like the guard and is not one is how the next
    # person comes to rely on it.
    if X.shape[1] < MIN_FEATURES:
        return _unscored(method, (
            f"{X.shape[1]} features, and {MIN_FEATURES} are needed before "
            f"looking at them jointly says anything the per-feature scores "
            f"do not already say."))

    standardised = _robust_standardise(X, x)
    if standardised is None:
        return _unscored(method, (
            "Fewer than four features vary at all across this machine's "
            "history. There is no shape here to learn."))
    Xs, xs = standardised

    try:
        from sklearn.ensemble import IsolationForest

        forest = IsolationForest(
            n_estimators=FOREST_TREES, random_state=RANDOM_SEED,
            contamination="auto",
        ).fit(Xs)
        training_scores = forest.score_samples(Xs)
        raw = float(forest.score_samples(xs.reshape(1, -1))[0])
    except Exception:
        logger.exception("Isolation Forest failed")
        return _unscored(method, "The detector failed to run.")

    # score_samples is higher for inliers, so a capture more isolated than
    # the whole training set sits below all of them.
    share_more_normal = float(np.mean(training_scores > raw))
    value = round(100.0 * share_more_normal, 1)

    return DetectorVerdict(
        method=method, scored=True, value=value, raw=round(raw, 5),
        reason=(f"This capture is more isolated from the machine's history "
                f"than {share_more_normal:.0%} of that history is from "
                f"itself. Judged across {Xs.shape[1]} features jointly, so "
                f"it can flag a combination that no single feature would."),
    )


def pca_residual_verdict(
    history: Sequence[Sequence[float]],
    reading: Sequence[float],
    feature_names: Sequence[str],
) -> DetectorVerdict:
    """How much of this capture does not fit the directions the machine moves in.

    Fitted with an SVD on the robustly standardised history, keeping the
    components that carry `PCA_VARIANCE_TARGET` of its variation, capped so
    the model can never have enough components to reconstruct anything put
    in front of it.

    The residual is decomposed per feature, because "this capture does not
    fit" is not actionable and "this capture does not fit, and it is the
    bearing bands that do not fit" is.
    """
    method = "pca_residual"
    X = np.asarray(history, dtype=float)
    x = np.asarray(reading, dtype=float)

    if X.ndim != 2 or X.shape[0] < MIN_TRAINING_SAMPLES:
        return _unscored(method, (
            f"{0 if X.ndim != 2 else X.shape[0]} captures of history, and "
            f"{MIN_TRAINING_SAMPLES} are needed. Fitted to less, the model "
            f"reconstructs its own training set exactly and every new "
            f"capture looks like residual."))
    if X.shape[1] < MIN_FEATURES:
        return _unscored(method, (
            f"{X.shape[1]} features, and {MIN_FEATURES} are needed."))

    usable = _usable_columns(X)
    standardised = _robust_standardise(X, x)
    if standardised is None:
        return _unscored(method, (
            "Fewer than four features vary at all across this machine's "
            "history. There are no directions here to learn."))
    Xs, xs = standardised
    names = [n for n, keep in zip(feature_names, usable) if keep]

    try:
        centre = Xs.mean(axis=0)
        centred = Xs - centre
        _, singular, components = np.linalg.svd(centred, full_matrices=False)

        variance = singular ** 2
        if variance.sum() <= 0:
            return _unscored(method, "This machine's history has no variation.")
        explained = np.cumsum(variance) / variance.sum()
        keep = int(np.searchsorted(explained, PCA_VARIANCE_TARGET) + 1)

        ceiling = max(1, int(min(Xs.shape) * PCA_MAX_COMPONENT_FRACTION))
        keep = max(1, min(keep, ceiling))

        basis = components[:keep]
        centred_reading = xs - centre
        # Project onto the subspace and back; what is left over is the part
        # the machine's history does not account for.
        reconstructed = (centred_reading @ basis.T) @ basis
        residual_vector = centred_reading - reconstructed
        raw = float(np.linalg.norm(residual_vector))

        training_residual = centred - (centred @ basis.T) @ basis
        training_raw = np.linalg.norm(training_residual, axis=1)
    except Exception:
        logger.exception("PCA residual failed")
        return _unscored(method, "The detector failed to run.")

    share_smaller = float(np.mean(training_raw < raw))
    value = round(100.0 * share_smaller, 1)

    squared = residual_vector ** 2
    total = float(squared.sum())
    drivers: list[tuple[str, float]] = []
    if total > 0:
        order = np.argsort(squared)[::-1][:5]
        drivers = [(names[i], float(squared[i] / total)) for i in order]

    leading = ", ".join(f"{n} ({s:.0%})" for n, s in drivers[:3])
    return DetectorVerdict(
        method=method, scored=True, value=value, raw=round(raw, 5),
        reason=(f"{keep} component(s) describe how this machine's history "
                f"varies, and this capture sits further outside them than "
                f"{share_smaller:.0%} of that history does. The part that "
                f"does not fit is mostly {leading}."
                if drivers else
                f"{keep} component(s) describe how this machine's history "
                f"varies, and this capture sits further outside them than "
                f"{share_smaller:.0%} of that history does."),
        drivers=drivers,
    )


def run_detectors(
    history: Sequence[Sequence[float]],
    reading: Sequence[float],
    feature_names: Sequence[str],
) -> list[DetectorVerdict]:
    """Both detectors on one capture. Neither is allowed to stop the other."""
    verdicts = []
    for run in (isolation_forest_verdict, pca_residual_verdict):
        try:
            verdicts.append(run(history, reading, feature_names))
        except Exception:
            logger.exception("%s raised", run.__name__)
            verdicts.append(_unscored(run.__name__, "The detector failed."))
    return verdicts
