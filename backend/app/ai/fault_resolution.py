"""Whether a spectrum can tell the diagnostic orders apart — VIK-050 support.

A fault is named by finding energy at one order and not at another. Outer
race sits at 3.064x on this pump and the third shaft harmonic at 3.000x; if
the spectrum cannot separate them, a bearing fault and a perfectly ordinary
harmonic produce the same picture and no amount of rule logic recovers the
difference.

That is the state this gateway is in, measured rather than feared. A 0.278 s
record gives 3.60 Hz per bin. BPFO and 3x are 1.58 Hz apart -- 0.44 of one
bin. They land in the same place. So do BPFI and the five-vane pass, and so
do the ball-spin frequency and 2x.

**Which makes the honest output "cannot tell", not "no fault found".** Those
two read identically on a screen and mean opposite things: one is a machine
that looks healthy, the other is an instrument that cannot see. Without this
check the fault engine returns an empty list in both cases, and an empty
list is read as good news.

The fix is not in software. Frequency resolution is one over the record
length, so separating BPFO from 3x on this machine needs about 1.9 s of
capture against the 0.278 s it takes now. The same lengthening also lets the
speed-steadiness check run, which is what currently stops any finding from
escalating.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

#: Bins two orders must be apart before a peak at one can be told from a
#: peak at the other.
#:
#: Three, not one. A discrete spectrum spreads a single tone across
#: neighbouring bins -- with a window, most of the energy lands in two or
#: three -- so two tones one bin apart do not appear as two peaks at all.
#: Three bins is the point at which a peak finder sees two maxima rather
#: than one broad one.
MIN_BIN_SEPARATION = 3.0

#: The pairs a diagnosis actually turns on, as orders of running speed.
#:
#: Every one of these is a bearing frequency against the shaft harmonic or
#: machine order it is most easily confused with. `bpfo` is not listed
#: against `1x` because nobody mistakes those; it is listed against `3x`
#: because on this pump they are 1.58 Hz apart.
CONFUSABLE = (
    ("bpfo", "3x shaft harmonic", 3.0),
    ("bpfi", "vane or blade pass", None),     # filled from the machine
    ("bsf", "2x shaft harmonic", 2.0),
    ("ftf", "sub-synchronous rub", 0.5),
)


@dataclass
class ResolutionVerdict:
    """What this spectrum can and cannot separate."""
    bin_hz: Optional[float] = None
    record_seconds: Optional[float] = None
    shaft_hz: Optional[float] = None
    #: Pairs that cannot be told apart, worst first.
    unresolved: list[dict[str, Any]] = field(default_factory=list)
    resolved: list[str] = field(default_factory=list)
    #: The record length that would separate everything listed above.
    needed_seconds: Optional[float] = None
    reason: str = ""

    @property
    def usable(self) -> bool:
        """Whether a bearing diagnosis from this spectrum means anything.

        Requires that pairs were actually compared, not merely that none
        came back unresolved. An earlier version asked only whether
        `unresolved` was empty, and it is empty in two opposite situations:
        everything separated cleanly, and nothing was ever checked because
        there was no shaft speed to place the orders against. That made
        "we could not look" report as "everything resolves" -- the same
        mistake, one layer up, that this whole module exists to prevent.
        """
        return bool(self.resolved) and not self.unresolved

    def as_dict(self) -> dict[str, Any]:
        return {
            "usable": self.usable, "bin_hz": self.bin_hz,
            "record_seconds": self.record_seconds,
            "unresolved": self.unresolved, "resolved": self.resolved,
            "needed_seconds": self.needed_seconds, "reason": self.reason,
        }


def assess_resolution(
    *,
    sample_rate_hz: Optional[float],
    sample_count: Optional[int],
    shaft_hz: Optional[float],
    bearing_orders: Optional[dict[str, Any]] = None,
    vane_pass_order: Optional[float] = None,
) -> ResolutionVerdict:
    """Can this capture separate the orders a bearing diagnosis needs?

    Returns a verdict rather than a boolean, because "no" is only useful
    with the numbers behind it: which pairs collide, how far apart they are,
    and how long a record would separate them. Somebody has to change a
    setting on the gateway, and they will want to know what to change it to.
    """
    verdict = ResolutionVerdict(shaft_hz=shaft_hz)

    if not sample_rate_hz or not sample_count or sample_count < 2:
        verdict.reason = ("The capture's length was not recorded, so what "
                          "this spectrum can separate is unknown.")
        return verdict

    seconds = float(sample_count) / float(sample_rate_hz)
    verdict.record_seconds = round(seconds, 4)
    verdict.bin_hz = round(1.0 / seconds, 4)

    if not shaft_hz or shaft_hz <= 0:
        verdict.reason = ("No shaft speed was established, so the orders "
                          "cannot be placed on the spectrum at all.")
        return verdict
    if not bearing_orders:
        verdict.reason = ("No bearing is resolved for this machine, so there "
                          "are no defect frequencies to separate.")
        return verdict

    worst_gap_hz: Optional[float] = None
    for defect, against, fixed_order in CONFUSABLE:
        order = bearing_orders.get(defect)
        if not order:
            continue
        neighbour = fixed_order if fixed_order is not None else vane_pass_order
        if not neighbour:
            continue

        gap_hz = abs(float(order) - float(neighbour)) * shaft_hz
        bins = gap_hz / verdict.bin_hz
        label = f"{defect.upper()} ({float(order):.3f}x) vs {against}"

        if bins >= MIN_BIN_SEPARATION:
            verdict.resolved.append(label)
            continue

        verdict.unresolved.append({
            "defect": defect, "against": against,
            "gap_hz": round(gap_hz, 3), "bins_apart": round(bins, 2),
            "statement": (f"{label} are {gap_hz:.2f} Hz apart and one bin is "
                          f"{verdict.bin_hz:.2f} Hz -- {bins:.2f} of a bin. "
                          f"They land in the same place."),
        })
        if gap_hz > 0 and (worst_gap_hz is None or gap_hz < worst_gap_hz):
            worst_gap_hz = gap_hz

    verdict.unresolved.sort(key=lambda item: item["bins_apart"])

    if worst_gap_hz:
        verdict.needed_seconds = round(MIN_BIN_SEPARATION / worst_gap_hz, 2)

    if verdict.unresolved:
        verdict.reason = (
            f"This {seconds:.3f} s record resolves {verdict.bin_hz:.2f} Hz "
            f"per bin, and {len(verdict.unresolved)} of the pairs a bearing "
            f"diagnosis turns on are closer together than that. A fault at "
            f"those frequencies and an ordinary shaft harmonic produce the "
            f"same picture, so the absence of a finding here is not evidence "
            f"the machine is healthy -- it is the instrument being unable to "
            f"tell. About {verdict.needed_seconds:.2f} s of capture would "
            f"separate them.")
    else:
        verdict.reason = (
            f"This {seconds:.3f} s record resolves {verdict.bin_hz:.2f} Hz "
            f"per bin, which separates every pair a bearing diagnosis turns "
            f"on.")
    return verdict
