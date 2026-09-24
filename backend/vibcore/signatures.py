"""Fault-signature matching — rank likely faults from a spectral peak list.

The rule table in ``data/fault_signatures.json`` does the ranking; retrieval
does the explaining. That split is deliberate: a rule table produces a
reproducible ordering with explicit matched and unmatched evidence, which pure
retrieval cannot do, while a textbook passage explains the mechanism, which a
rule table cannot do. The graph fires one targeted search per top hypothesis
using each rule's ``query_hint``.

``SpectralPeak`` is the pivot of the whole design. Peaks computed from a
waveform and peaks read off an analyser screenshot by the vision model produce
*the same* structure, differing only in ``source`` and ``confidence``. Every
downstream consumer — this matcher, the bearing cross-check, the diagnosis —
therefore works identically whichever way the data arrived.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from vibcore.records import ComputationRecord, FormulaSource

DATA_PATH = Path(__file__).parent / "data" / "fault_signatures.json"

PeakSource = Literal["waveform", "chart_vlm", "user"]
Direction = Literal["H", "V", "A", ""]

# A peak within this distance of an integer order is treated as synchronous.
SYNCHRONOUS_TOLERANCE = 0.02

# A "dominant" order must reach this fraction of the largest peak in the
# spectrum. Set high on purpose: at 0.7 a 2x sitting well below a larger 1x
# still counted as dominant, so misalignment outranked looseness on a spectrum
# whose largest peak was 1x.
DOMINANCE_THRESHOLD = 0.85

# Multiplier applied to axial-signature faults (angular misalignment, bent
# shaft) when no axial measurement is present. They are *defined* by axial
# dominance, so without axial data they stay in the list as something to rule
# out — but must not outrank a fault the radial data actually supports.
NO_AXIAL_PENALTY = 0.55


@dataclass
class SpectralPeak:
    """One peak in a spectrum, however it was obtained.

    ``order`` is frequency divided by shaft rate. It is optional because a
    chart may be read before the running speed is known; :func:`assign_orders`
    fills it in once a shaft speed is available.
    """

    frequency_hz: float
    amplitude: float
    order: float | None = None
    direction: Direction = ""
    sidebands_hz: list[float] = field(default_factory=list)
    label: str = ""
    source: PeakSource = "user"
    confidence: float = 1.0

    @property
    def is_synchronous(self) -> bool:
        """True when the peak sits on an integer multiple of running speed.

        Bearing defect frequencies are irrational multiples of shaft rate, so
        non-synchronous is the first thing that separates a bearing fault from
        unbalance or misalignment.
        """
        if self.order is None:
            return False
        return abs(self.order - round(self.order)) < SYNCHRONOUS_TOLERANCE

    def as_dict(self) -> dict[str, Any]:
        return {
            "frequency_hz": round(self.frequency_hz, 3),
            "amplitude": round(self.amplitude, 6),
            "order": round(self.order, 4) if self.order is not None else None,
            "direction": self.direction,
            "is_synchronous": self.is_synchronous,
            "label": self.label,
            "source": self.source,
            "confidence": self.confidence,
        }


@dataclass
class MachineContext:
    """Everything the rule table needs beyond the peaks themselves.

    Populated from a stored MachineProfile where one exists, otherwise from
    whatever the user stated. Missing entries simply disable the rules that
    depend on them — a machine with no gearbox never gets a gear-mesh
    hypothesis, rather than getting a bad one.
    """

    shaft_rpm: float | None = None
    bearing_orders: dict[str, float] = field(default_factory=dict)
    gear_mesh_orders: list[float] = field(default_factory=list)
    vane_pass_order: float | None = None
    line_freq_hz: float | None = None
    belt_order: float | None = None
    has_journal_bearings: bool = False
    has_rolling_bearings: bool = True

    @property
    def shaft_hz(self) -> float | None:
        return self.shaft_rpm / 60.0 if self.shaft_rpm else None


@dataclass
class Evidence:
    statement: str
    order: float | None = None
    frequency_hz: float | None = None
    amplitude: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "statement": self.statement,
            "order": round(self.order, 4) if self.order is not None else None,
            "frequency_hz": round(self.frequency_hz, 3) if self.frequency_hz else None,
            "amplitude": round(self.amplitude, 6) if self.amplitude is not None else None,
        }


@dataclass
class FaultHypothesis:
    fault_key: str
    name: str
    score: float
    confidence: float
    evidence: list[Evidence] = field(default_factory=list)
    contradicting_evidence: list[Evidence] = field(default_factory=list)
    mechanism: str = ""
    confirming_checks: list[str] = field(default_factory=list)
    query_hint: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "fault": self.name,
            "fault_key": self.fault_key,
            "score": round(self.score, 3),
            "confidence": round(self.confidence, 3),
            "evidence": [e.as_dict() for e in self.evidence],
            "contradicting_evidence": [e.as_dict() for e in self.contradicting_evidence],
            "mechanism": self.mechanism,
            "confirming_checks": self.confirming_checks,
        }


@lru_cache(maxsize=1)
def _rules() -> dict[str, Any]:
    with DATA_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)["rules"]


def assign_orders(peaks: list[SpectralPeak], shaft_rpm: float) -> list[SpectralPeak]:
    """Fill in ``order`` on peaks that only carry a frequency."""
    if shaft_rpm <= 0:
        raise ValueError("shaft_rpm must be positive")
    shaft_hz = shaft_rpm / 60.0
    for peak in peaks:
        if peak.order is None:
            peak.order = peak.frequency_hz / shaft_hz
    return peaks


# --------------------------------------------------------------------------
# Order reference resolution
# --------------------------------------------------------------------------

_MULTIPLIER_RE = re.compile(r"^(?P<base>@?[a-z_0-9.]+)(?:\*(?P<mult>[0-9.]+))?$")


def _resolve_ref(ref: str, ctx: MachineContext) -> list[float] | None:
    """Resolve an order reference to concrete order values.

    Returns ``None`` when the reference depends on machine context that is not
    available, which causes the whole rule to be skipped. A list is returned
    because a multi-stage gearbox has several mesh frequencies.
    """
    match = _MULTIPLIER_RE.match(ref.strip().lower())
    if not match:
        return None
    base, mult_text = match.group("base"), match.group("mult")
    multiplier = float(mult_text) if mult_text else 1.0

    if not base.startswith("@"):
        try:
            return [float(base) * multiplier]
        except ValueError:
            return None

    key = base[1:]
    if key in ("bpfo", "bpfi", "bsf", "ftf", "bsf2x"):
        value = ctx.bearing_orders.get(key)
        return [value * multiplier] if value else None
    if key == "gmf":
        return [g * multiplier for g in ctx.gear_mesh_orders] or None
    if key in ("vane_pass", "blade_pass"):
        return [ctx.vane_pass_order * multiplier] if ctx.vane_pass_order else None
    if key == "line_2x":
        if not (ctx.line_freq_hz and ctx.shaft_hz):
            return None
        # Electrical faults are pinned to supply frequency, not shaft speed, so
        # the order depends on the actual running speed.
        return [(2.0 * ctx.line_freq_hz / ctx.shaft_hz) * multiplier]
    if key == "belt":
        return [ctx.belt_order * multiplier] if ctx.belt_order else None
    return None


def _find_peak(
    peaks: list[SpectralPeak],
    target_order: float,
    tol_order: float | None,
    tol_pct: float | None,
) -> SpectralPeak | None:
    """Closest peak to ``target_order`` within tolerance, if any."""
    tolerance = tol_order if tol_order is not None else target_order * (tol_pct or 1.0) / 100.0
    best: SpectralPeak | None = None
    best_distance = float("inf")
    for peak in peaks:
        if peak.order is None:
            continue
        distance = abs(peak.order - target_order)
        if distance <= tolerance and distance < best_distance:
            best, best_distance = peak, distance
    return best


def _rule_applies(key: str, rule: dict[str, Any], ctx: MachineContext) -> bool:
    """Filter out rules that cannot physically apply to this machine."""
    if key == "oil_whirl" and not ctx.has_journal_bearings:
        return False
    if key.startswith("bearing_") and not ctx.has_rolling_bearings:
        return False
    return True


def match_faults(
    peaks: list[SpectralPeak],
    context: MachineContext | None = None,
    top_n: int = 5,
    min_score: float = 0.05,
) -> list[FaultHypothesis]:
    """Rank fault hypotheses against a peak list.

    Scoring: matched dominant/required/supporting weights, minus half the
    weight of any contradicting order that is present, over the total available
    weight. A missing dominant or required order disqualifies the rule.
    """
    ctx = context or MachineContext()
    usable = [p for p in peaks if p.order is not None]
    if not usable:
        return []

    max_amplitude = max(p.amplitude for p in usable) or 1.0
    hypotheses: list[FaultHypothesis] = []

    for key, rule in _rules().items():
        if not _rule_applies(key, rule, ctx):
            continue

        matched_weight = 0.0
        available_weight = 0.0
        contradiction_weight = 0.0
        evidence: list[Evidence] = []
        contradicting: list[Evidence] = []
        matched_peaks: list[SpectralPeak] = []
        disqualified = False
        unresolvable = False

        for spec in rule["orders"]:
            role = spec["role"]
            weight = float(spec["weight"])
            targets = _resolve_ref(spec["ref"], ctx)

            if targets is None:
                # Context missing. A dominant/required order we cannot resolve
                # means the rule is untestable, not that it failed.
                if role in ("dominant", "required"):
                    unresolvable = True
                    break
                continue

            hit: SpectralPeak | None = None
            hit_target = 0.0
            for target in targets:
                found = _find_peak(usable, target, spec.get("tol_order"), spec.get("tol_pct"))
                if found is not None:
                    hit, hit_target = found, target
                    break

            if role == "contradicting":
                if hit is not None:
                    # Scaled by how large the contradicting peak actually is. A
                    # small 2x alongside a dominant 1x is normal for unbalance;
                    # only a 2x comparable to the 1x argues against it. Charging
                    # the full weight regardless would rank the correct answer
                    # below rules that simply list fewer contradictions.
                    relative = hit.amplitude / max_amplitude
                    contradiction_weight += weight * relative
                    contradicting.append(
                        Evidence(
                            statement=f"{spec['ref']}x present at {relative:.0%} of the "
                            f"largest peak, which argues against {rule['name'].lower()}",
                            order=hit.order,
                            frequency_hz=hit.frequency_hz,
                            amplitude=hit.amplitude,
                        )
                    )
                continue

            available_weight += weight

            if hit is None:
                if role in ("dominant", "required"):
                    disqualified = True
                    break
                continue

            if role == "dominant" and hit.amplitude < DOMINANCE_THRESHOLD * max_amplitude:
                # Present but not actually dominant — the signature does not fit.
                disqualified = True
                contradicting.append(
                    Evidence(
                        statement=f"Expected {spec['ref']}x to dominate, but it is only "
                        f"{hit.amplitude / max_amplitude:.0%} of the largest peak",
                        order=hit.order,
                        frequency_hz=hit.frequency_hz,
                        amplitude=hit.amplitude,
                    )
                )
                break

            matched_weight += weight
            matched_peaks.append(hit)
            evidence.append(
                Evidence(
                    statement=f"{spec['ref']} matched at {hit.frequency_hz:.2f} Hz "
                    f"({hit.order:.3f}x, {hit.amplitude / max_amplitude:.0%} of peak)"
                    + (f" [expected {hit_target:.3f}x]" if spec["ref"].startswith("@") else ""),
                    order=hit.order,
                    frequency_hz=hit.frequency_hz,
                    amplitude=hit.amplitude,
                )
            )

        if disqualified or unresolvable or available_weight <= 0:
            continue

        score = (matched_weight - 0.5 * contradiction_weight) / available_weight
        score = max(0.0, min(1.0, score))
        if score < min_score:
            continue

        # Direction is a strong discriminator when it is available. Angular
        # misalignment and a bent shaft are axial faults; without an axial
        # measurement they cannot be separated from radial ones, so a rule that
        # wants axial evidence and does not get it is held back rather than
        # ruled out.
        directions = {p.direction for p in matched_peaks if p.direction}
        if rule.get("requires_axial"):
            if "A" in directions:
                score = min(1.0, score * 1.15)
                evidence.append(Evidence(statement="Axial measurement supports this fault."))
            elif directions:
                score *= 0.6
                contradicting.append(
                    Evidence(
                        statement="This fault is characteristically axial, but the "
                        "matched peaks are radial."
                    )
                )
            else:
                score *= NO_AXIAL_PENALTY
                contradicting.append(
                    Evidence(
                        statement="No axial measurement supplied — this fault cannot be "
                        "confirmed or excluded without one."
                    )
                )

        # Confidence is bounded by the least reliable peak that supports it, so
        # a hypothesis built on VLM-read chart values can never be reported as
        # firmly as one built on a computed waveform.
        peak_confidence = min((p.confidence for p in matched_peaks), default=1.0)

        hypotheses.append(
            FaultHypothesis(
                fault_key=key,
                name=rule["name"],
                score=score,
                confidence=round(score * peak_confidence, 3),
                evidence=evidence,
                contradicting_evidence=contradicting,
                mechanism=rule.get("mechanism", ""),
                confirming_checks=rule.get("confirming_checks", []),
                query_hint=rule.get("query_hint", ""),
            )
        )

    hypotheses.sort(key=lambda h: (h.score, h.confidence), reverse=True)
    return hypotheses[:top_n]


def cross_check_bearing_peaks(
    peaks: list[SpectralPeak], bearing_orders: dict[str, float], tol_pct: float = 1.5
) -> list[str]:
    """Label non-synchronous peaks that match a computed bearing frequency.

    This is the join between computed geometry and observed data, and the
    single most diagnostic thing the system does: it turns "an unexplained peak
    at 3.58x" into "BPFO for the fitted bearing, within 0.4%".
    """
    notes: list[str] = []
    for peak in peaks:
        if peak.order is None or peak.is_synchronous:
            continue
        for name, order in bearing_orders.items():
            if not order:
                continue
            deviation = abs(peak.order - order) / order * 100.0
            if deviation <= tol_pct:
                label = name.upper()
                peak.label = peak.label or label
                notes.append(
                    f"Non-synchronous peak at {peak.frequency_hz:.2f} Hz ({peak.order:.3f}x) "
                    f"matches computed {label} ({order:.3f}x) within {deviation:.2f}%."
                )
                break
    return notes


def build_record(
    hypotheses: list[FaultHypothesis],
    peaks: list[SpectralPeak],
    ctx: MachineContext,
    cross_check_notes: list[str],
) -> ComputationRecord:
    return ComputationRecord(
        tool="match_fault_signatures",
        inputs={
            "peak_count": len(peaks),
            "shaft_rpm": ctx.shaft_rpm,
            "peaks": [p.as_dict() for p in peaks[:12]],
            "bearing_orders": {k: round(v, 4) for k, v in ctx.bearing_orders.items()},
        },
        outputs={
            "hypotheses": [h.as_dict() for h in hypotheses],
            "bearing_cross_check": cross_check_notes,
        },
        formula=(
            "Rule-table match on orders of running speed. "
            "score = (matched weight - 0.5 x contradicting weight) / available weight; "
            "a missing dominant or required order disqualifies the rule."
        ),
        formula_source=FormulaSource(
            kind="textbook",
            ref="Spectral fault signature tables",
            query_hint=(
                "vibration fault signature chart diagnosis unbalance misalignment "
                "looseness bearing harmonics orders running speed"
            ),
        ),
        assumptions=[
            "Ranking is based on spectral orders alone. Phase measurements, "
            "directional comparison (H/V/A), and trend history all carry "
            "diagnostic information not used here and can change the ordering.",
        ],
        confidence=min((p.confidence for p in peaks), default=1.0),
    )


def summarize(hypotheses: list[FaultHypothesis], cross_check_notes: list[str]) -> str:
    if not hypotheses:
        return "No fault signature matched the supplied peaks."
    lines: list[str] = []
    for i, h in enumerate(hypotheses, start=1):
        lines.append(f"{i}. {h.name} — score {h.score:.2f}, confidence {h.confidence:.2f}")
        for e in h.evidence[:4]:
            lines.append(f"     + {e.statement}")
        for e in h.contradicting_evidence[:2]:
            lines.append(f"     - {e.statement}")
    if cross_check_notes:
        lines.append("Bearing cross-check:")
        lines.extend(f"     * {note}" for note in cross_check_notes)
    return "\n".join(lines)
