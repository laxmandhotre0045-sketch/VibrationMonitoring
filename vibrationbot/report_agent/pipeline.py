"""The report pipeline: declared steps, isolated failures, one ledger.

Same shape as the measurement pipeline proposed for the backend, and for the
same reasons. Steps declare what they need rather than depending on the order
they were written in, a step that fails marks its section incomplete instead of
losing the whole report, and the orchestrator itself contains no vibration
knowledge -- only names and dependencies.

Phase 1 is deliberately model-free. Everything here is measured or computed,
and the report is complete and useful before any prose is generated. That
ordering is the main lesson from the knowledge agent: the parts built
model-first needed the most rework.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from report_agent import sources
from report_agent.ledger import Ledger

logger = logging.getLogger(__name__)


@dataclass
class ReportContext:
    """What a report is being written about, and what has been found so far."""

    sensor: str
    from_date: str | None = None
    to_date: str | None = None
    max_captures: int = 200
    power_kw: float | None = None
    foundation: str | None = None
    integrated_driver: bool | None = None
    acceleration_unit: str | None = None

    ledger: Ledger = field(default_factory=Ledger)
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class StepOutcome:
    name: str
    status: str          # "ok" | "failed" | "skipped"
    detail: str = ""
    error: str = ""
    ms: int = 0


@dataclass(frozen=True)
class Step:
    name: str
    run: Callable[[ReportContext], str]
    requires: tuple[str, ...] = ()
    #: A section the reader would notice missing, so its failure is reported
    #: in the report itself rather than only in the log.
    section: str = ""


@dataclass
class ReportResult:
    ok: bool
    context: ReportContext
    outcomes: dict[str, StepOutcome] = field(default_factory=dict)
    rendered: dict[str, str] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    def failed(self, name: str) -> bool:
        outcome = self.outcomes.get(name)
        return outcome is not None and outcome.status == "failed"

    def incomplete_sections(self) -> list[str]:
        return [
            o.name for o in self.outcomes.values()
            if o.status in ("failed", "skipped")
        ]


# --------------------------------------------------------------------------
# Steps
# --------------------------------------------------------------------------


def _collect(ctx: ReportContext) -> str:
    dataset = sources.collect_measurements(
        ctx.ledger, ctx.sensor,
        from_date=ctx.from_date, to_date=ctx.to_date, max_captures=ctx.max_captures,
    )
    if not dataset.get("ok"):
        raise RuntimeError(dataset.get("error", "no measurement data"))
    ctx.data["dataset"] = dataset
    return f"{dataset['captures']} captures, {len(dataset['rows'])} rows"


def _integrity(ctx: ReportContext) -> str:
    check = sources.detect_identical_captures(ctx.data["dataset"])
    ctx.data["integrity"] = check
    return "identical captures detected" if check["identical"] else "captures differ"


def _features(ctx: ReportContext) -> str:
    summary = sources.summarise_features(ctx.ledger, ctx.data["dataset"])
    ctx.data["features"] = summary
    worst = [f for f in summary if f["worst_status"] == "critical"]
    return f"{len(summary)} features, {len(worst)} with a critical reading"


def _iso(ctx: ReportContext) -> str:
    identity = ctx.data["dataset"]["identity"]
    reference = sources.iso_reference(
        ctx.ledger, identity.get("machine_type") or "machine",
        power_kw=ctx.power_kw, foundation=ctx.foundation,
        integrated_driver=ctx.integrated_driver,
    )
    # Comparable only when the platform's stored unit is the standard's unit.
    units = set(ctx.data["dataset"].get("units_seen") or [])
    reference["comparable"] = units == {"mm/s"} or units == {"mm/s RMS"}
    reference["units_seen"] = sorted(units)
    ctx.data["iso"] = reference
    if not reference.get("ok"):
        return reference.get("reason", "group unknown")
    return f"{len(reference['tables'])} reference table(s); comparable={reference['comparable']}"


def _shaft(ctx: ReportContext) -> str:
    shaft = sources.derive_shaft_speed(ctx.ledger, ctx.data["dataset"])
    ctx.data["shaft"] = shaft
    return f"{shaft['rpm']} rpm ({shaft['confidence']}% of channels agree)" if shaft["ok"] else shaft["reason"][:60]


def _velocity(ctx: ReportContext) -> str:
    velocity = sources.convert_to_velocity(
        ctx.ledger, ctx.data["dataset"], ctx.data.get("shaft") or {}, ctx.acceleration_unit
    )
    ctx.data["velocity"] = velocity
    if not velocity.get("ok"):
        return "not converted - acceleration unit unstated"
    # A 1X velocity far above the standard's damage boundary is not a machine
    # in that state; it is data that is synthetic, mis-scaled, or in units
    # other than assumed. Saying so is more useful than grading it.
    worst_boundary = 11.0
    velocity["implausible"] = velocity["velocity_mm_s"] > worst_boundary * 2
    return f"1X = {velocity['velocity_mm_s']} mm/s ({velocity['assumption']})"


def _calibration(ctx: ReportContext) -> str:
    check = sources.assess_threshold_calibration(ctx.data["dataset"])
    ctx.data["calibration"] = check
    return (f"{len(check['suspect'])} feature(s) look uncalibrated"
            if check["suspect"] else "thresholds look calibrated")


def _assess(ctx: ReportContext) -> str:
    """Decide the headline, from status counts only.

    Deliberately not an ISO verdict. The platform's thresholds produced these
    statuses against this sensor's own baseline; the ISO tables are reference
    only while the units differ. Mixing the two would produce a severity the
    data does not support.
    """
    counts = ctx.data["dataset"].get("status_counts") or {}
    critical, warning = counts.get("critical", 0), counts.get("warning", 0)
    no_baseline = counts.get("no_baseline", 0)
    total = sum(counts.values()) or 1

    calibration = ctx.data.get("calibration") or {}
    suspect = {f["code"] for f in calibration.get("suspect", [])}
    # Criticals that come only from features whose thresholds look
    # uncalibrated are not evidence of a fault, and must not drive an
    # "action required" headline.
    trustworthy_critical = [
        r for r in (ctx.data["dataset"].get("rows") or [])
        if r.get("status") == "critical" and r.get("feature_code") not in suspect
    ]

    if suspect and not trustworthy_critical:
        headline, urgency = "Not assessable - thresholds need calibrating", "unknown"
    elif trustworthy_critical:
        headline, urgency = "Action required", "critical"
    elif critical:
        headline, urgency = "Action required", "critical"
    elif warning:
        headline, urgency = "Investigate", "warning"
    elif no_baseline == total:
        headline, urgency = "Not assessed", "unknown"
    else:
        headline, urgency = "No action", "normal"

    # Fact ids, not values. The template references these through ref() so the
    # summary prose carries no number the ledger did not supply -- the
    # verifier rejected an earlier version of this template for exactly that.
    ids = ctx.data["dataset"].get("fact_ids") or {}
    ctx.data["assessment"] = {
        "headline": headline,
        "urgency": urgency,
        "critical": critical,
        "warning": warning,
        "no_baseline": no_baseline,
        "total": total,
        "trustworthy_critical": len(trustworthy_critical),
        "uncalibrated_features": sorted(suspect),
        "critical_fact": ids.get("critical"),
        "warning_fact": ids.get("warning"),
        "no_baseline_fact": ids.get("no_baseline"),
        "rows_fact": ids.get("rows"),
        "channels_fact": ids.get("channels"),
    }
    return f"{headline} ({critical} critical of {total})"


STEPS: tuple[Step, ...] = (
    Step("collect", _collect, section="Measurement"),
    Step("integrity", _integrity, requires=("collect",), section="Data integrity"),
    Step("features", _features, requires=("collect",), section="Feature summary"),
    Step("iso", _iso, requires=("collect",), section="ISO reference"),
    Step("shaft", _shaft, requires=("collect",), section="Shaft speed"),
    Step("velocity", _velocity, requires=("collect", "shaft"), section="Velocity conversion"),
    Step("calibration", _calibration, requires=("collect",), section="Threshold calibration"),
    Step("assess", _assess, requires=("collect", "calibration"), section="Executive summary"),
)

STEP_NAMES = tuple(s.name for s in STEPS)


# --------------------------------------------------------------------------


def build_report(ctx: ReportContext) -> ReportResult:
    """Run every step, then render. A failed step costs its section, not the report."""
    result = ReportResult(ok=True, context=ctx)
    started = time.perf_counter()

    for step in STEPS:
        missing = [
            name for name in step.requires
            if result.outcomes.get(name) is None
            or result.outcomes[name].status != "ok"
        ]
        if missing:
            result.outcomes[step.name] = StepOutcome(
                step.name, "skipped", detail=f"requires {', '.join(missing)}"
            )
            continue

        step_started = time.perf_counter()
        try:
            detail = step.run(ctx)
        except Exception as exc:  # noqa: BLE001 - one section must not cost the rest
            logger.warning("Report step %s failed: %s", step.name, exc)
            result.outcomes[step.name] = StepOutcome(
                step.name, "failed", error=str(exc),
                ms=int((time.perf_counter() - step_started) * 1000),
            )
            continue
        result.outcomes[step.name] = StepOutcome(
            step.name, "ok", detail=detail,
            ms=int((time.perf_counter() - step_started) * 1000),
        )

    result.ok = not any(o.status == "failed" for o in result.outcomes.values())
    ctx.data["meta"] = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "incomplete": [
            {"section": s.section, "why": result.outcomes[s.name].error
             or result.outcomes[s.name].detail}
            for s in STEPS
            if result.outcomes.get(s.name) and result.outcomes[s.name].status != "ok"
        ],
        "steps": [result.outcomes[n].__dict__ for n in STEP_NAMES if n in result.outcomes],
    }
    return result
