"""Which condition the machine was running in — VIK-039.

A pump at low load and the same pump at high load produce different
vibration while both are perfectly healthy. A baseline built across the two
is the average of neither, so every capture sits some distance from a normal
that describes no state the machine has ever been in -- and the distance
looks exactly like a fault. That is why the requirement says baseline and
anomaly detection must be mode-wise, and this is the part that decides which
mode a capture belongs to.

**Banding before clustering, and the ticket says so.** The bands a plant
engineer can write down are better evidence than anything discovered from
history, because they encode what the machine is *for*. Clustering is worth
having later for machines nobody has characterised; it is not worth having
instead.

**Unknown is an answer, and usually the right one.** A capture that matches
no configured band is labelled unknown and stops there. The temptation is to
take the nearest band, and it is the wrong thing to do twice over: the
capture joins a baseline it does not belong to and widens that mode's
spread, which is precisely how a real fault comes to look ordinary. The same
rule as "no baseline is not normal", one layer down.

That has a consequence worth stating plainly: on a machine nobody has
configured modes for, *every* capture is unknown. That is not the engine
failing. It is the engine declining to invent the one piece of information
it was never given, and it is why `reason` always says which of the several
kinds of unknown this is.

**What it does not use.** The requirement lists current, power, process
signal and a machine state tag among the inputs. None of them reaches this
platform today -- there is no column for any of them -- so this works from
shaft speed and vibration level, and says so. Adding them later is a change
to `detect_mode`'s inputs, not to the shape of its answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

UNKNOWN = "unknown"
OFF = "off"

#: Vibration level below which the machine is not running at all, in g RMS.
#:
#: Measured against this gateway: the quietest real channel on the running
#: pump sits at 0.0023 g, and a stopped machine reads the converter's own
#: noise -- about one step, 0.0015 g. A tenth of the quietest running
#: channel separates the two without needing a band configured for it,
#: which matters because "off" is the one mode nobody bothers to write down.
OFF_LEVEL_G = 0.0002

#: And the shaft must be stopped too. Level alone would call a healthy
#: machine on a very quiet mounting "off".
OFF_SHAFT_HZ = 0.5

#: How far inside a band a capture must sit to be called a confident match.
#: At the centre the confidence is 1.0, at the edge it is this. A capture on
#: a boundary genuinely could be either side, and reporting that as certain
#: would hide a real ambiguity from whoever reads the finding later.
EDGE_CONFIDENCE = 0.5

#: Below this, the match is too weak to act on and the verdict is unknown
#: even though a band technically contained it.
MIN_CONFIDENCE = 0.35


@dataclass
class ModeBand:
    """One configured operating mode: a label and the band that defines it."""
    id: Optional[str]
    label: str
    rpm_min: Optional[float] = None
    rpm_max: Optional[float] = None
    load_min: Optional[float] = None
    load_max: Optional[float] = None
    source: str = "configured"

    @property
    def bounded(self) -> bool:
        """Whether this band constrains speed at all.

        A row with neither end set matches every capture, which would make
        every other band unreachable. Treated as unusable rather than as a
        catch-all.
        """
        return self.rpm_min is not None or self.rpm_max is not None

    def contains(self, rpm: float) -> bool:
        if self.rpm_min is not None and rpm < self.rpm_min:
            return False
        if self.rpm_max is not None and rpm > self.rpm_max:
            return False
        return True

    def fit(self, rpm: float) -> float:
        """1.0 at the centre of the band, falling to EDGE_CONFIDENCE at its
        edges. An open-ended band cannot have a centre, so anything inside it
        scores the edge value -- honest rather than generous."""
        if not self.contains(rpm):
            return 0.0
        if self.rpm_min is None or self.rpm_max is None:
            return EDGE_CONFIDENCE
        width = self.rpm_max - self.rpm_min
        if width <= 0:
            return 1.0
        centre = (self.rpm_min + self.rpm_max) / 2.0
        distance = abs(rpm - centre) / (width / 2.0)
        return EDGE_CONFIDENCE + (1.0 - EDGE_CONFIDENCE) * (1.0 - min(distance, 1.0))


@dataclass
class ModeVerdict:
    """Which mode a capture was in, and how much that is worth."""
    label: str = UNKNOWN
    mode_id: Optional[str] = None
    is_unknown: bool = True
    confidence: float = 0.0
    shaft_hz: Optional[float] = None
    shaft_source: Optional[str] = None
    overall_level: Optional[float] = None
    stability: Optional[str] = None
    reason: str = ""
    candidates: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label, "mode_id": self.mode_id,
            "is_unknown": self.is_unknown, "confidence": self.confidence,
            "shaft_hz": self.shaft_hz, "shaft_source": self.shaft_source,
            "overall_level": self.overall_level, "stability": self.stability,
            "reason": self.reason, "candidates": self.candidates,
        }


def _unknown(reason: str, **kw: Any) -> ModeVerdict:
    return ModeVerdict(label=UNKNOWN, is_unknown=True, confidence=0.0,
                       reason=reason, **kw)


def detect_mode(
    bands: list[ModeBand],
    *,
    shaft_hz: Optional[float] = None,
    shaft_usable: bool = False,
    shaft_source: Optional[str] = None,
    overall_level_g: Optional[float] = None,
    stability: Optional[str] = None,
) -> ModeVerdict:
    """Decide the operating mode for one capture.

    `shaft_usable` matters as much as `shaft_hz`. The speed estimator returns
    a number even when it could not establish one -- the tallest line in the
    spectrum, which on this pump is four times the true speed -- and banding
    against that would put every capture in the wrong mode with full
    confidence. An unusable speed is treated as no speed.
    """
    common = {"shaft_hz": shaft_hz, "shaft_source": shaft_source,
              "overall_level": overall_level_g, "stability": stability}

    # Stopped, which is decidable without anybody configuring a band for it.
    if (overall_level_g is not None and overall_level_g < OFF_LEVEL_G
            and (not shaft_usable or not shaft_hz or shaft_hz < OFF_SHAFT_HZ)):
        return ModeVerdict(
            label=OFF, is_unknown=False, confidence=1.0,
            reason=(f"Vibration is {overall_level_g:.5f} g, below the "
                    f"{OFF_LEVEL_G:g} g at which this machine registers as "
                    f"running, and no shaft speed was established. The "
                    f"machine is stopped."),
            **common)

    usable = [b for b in bands if b.bounded]
    if not usable:
        return _unknown(
            "No operating modes are configured for this machine, so there is "
            "nothing to match a capture against. Every capture will be "
            "unknown until somebody defines the bands -- which is the honest "
            "state, not a failure: the engine cannot invent what load the "
            "machine was under.", **common)

    if not shaft_usable or not shaft_hz or shaft_hz <= 0:
        return _unknown(
            "The shaft speed could not be established for this capture, and "
            "every configured mode is a speed band. Guessing from the "
            "tallest line in the spectrum is what the speed estimator "
            "already refused to do, and banding on that refusal would put "
            "the capture in a mode with false confidence.", **common)

    rpm = shaft_hz * 60.0
    scored = sorted(((b.fit(rpm), b) for b in usable if b.contains(rpm)),
                    key=lambda pair: -pair[0])

    if not scored:
        edges = ", ".join(
            f"{b.label} "
            f"{'' if b.rpm_min is None else format(b.rpm_min, '.0f')}"
            f"-{'' if b.rpm_max is None else format(b.rpm_max, '.0f')}"
            for b in usable)
        return _unknown(
            f"The shaft was turning at {rpm:.0f} rpm, which falls in none of "
            f"this machine's configured modes ({edges}). Labelled unknown "
            f"rather than assigned to the nearest: a capture in the wrong "
            f"mode widens that mode's normal, and a fault inside a widened "
            f"normal stops looking like one.", **common)

    confidence, best = scored[0]
    others = [b.label for _, b in scored[1:]]

    reason = (f"The shaft was turning at {rpm:.0f} rpm, inside the "
              f"{best.label} band.")
    if others:
        reason += (f" {len(others)} other band(s) also contain it "
                   f"({', '.join(others)}); the closest fit wins and the rest "
                   f"are recorded, because overlapping bands are a "
                   f"configuration problem somebody should see.")
    if stability in ("variable", "unstable"):
        # The speed is inside the band but did not hold there. Reported, and
        # the confidence is cut, because a baseline built from captures whose
        # speed was moving describes a machine that was never at one speed.
        confidence *= 0.5
        reason += (f" The speed was {stability} across the record, so this "
                   f"is a weaker match than the band alone suggests.")

    # One gate, applied after every adjustment. There were two, and the
    # first one -- before the instability penalty -- could never fire:
    # `fit` floors at EDGE_CONFIDENCE for anything inside a band, and that
    # floor sits above MIN_CONFIDENCE. A check that cannot fail is not a
    # check, and reading like one is worse than not being there.
    if confidence < MIN_CONFIDENCE:
        return _unknown(
            reason + (f" That leaves a confidence of {confidence:.2f}, below "
                      f"the {MIN_CONFIDENCE} needed to build a normal on, so "
                      f"the capture is left unassigned rather than counted "
                      f"towards a mode it only barely matches."),
            candidates=[best.label] + others, **common)

    return ModeVerdict(
        label=best.label, mode_id=best.id, is_unknown=False,
        confidence=round(confidence, 3), reason=reason,
        candidates=others, **common)
