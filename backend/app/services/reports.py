"""Automatic reports — section 17.

Section 17.1 lists eighteen things a report should contain and 17.2 lists
nine kinds of report. Almost all of the content already exists somewhere in
the platform; a report is the act of gathering it for one audience and one
period, which is why this module composes the existing services rather than
computing anything new.

**A report says what it could not include.** Every section here can come
back empty for a real reason -- no findings because the spectrum cannot
resolve them, no RUL because the history is five days, no analyst comments
because nobody has commented. A report that silently omits those reads as a
clean bill of health, and a monthly reliability report that looks clean
because half its inputs were missing is the most expensive document this
platform could produce.

**Plots are referenced, not rendered.** Section 17.1 asks for trend, FFT,
envelope and waveform plots. Those are generated and stored already, so the
report carries the pointers and what to look for on each -- the mapping
VIK-059 built. Redrawing them here would create a second set that could
disagree with the screens.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.fault_storage import open_findings
from app.services.fleet_storage import fleet
from app.services.governance import summary as governance_summary
from app.services.health_storage import (
    capture_symptoms,
    plots_for,
    sensor_health,
    sensor_reliability,
    sensor_rul,
)

logger = logging.getLogger(__name__)

#: Section 17.2's nine report types, with the window each covers.
REPORT_TYPES: dict[str, dict[str, Any]] = {
    "daily_summary": {
        "name": "Daily AI summary", "days": 1, "scope": "fleet"},
    "weekly_machine_health": {
        "name": "Weekly machine health report", "days": 7, "scope": "machine"},
    "monthly_reliability": {
        "name": "Monthly reliability report", "days": 30, "scope": "machine"},
    "critical_alarms": {
        "name": "Critical alarm report", "days": 7, "scope": "fleet"},
    "fault_evolution": {
        "name": "Fault evolution report", "days": 90, "scope": "machine"},
    "bearing_defect": {
        "name": "Bearing defect report", "days": 90, "scope": "machine",
        "faults": ("bearing_outer_race", "bearing_inner_race",
                   "bearing_ball_defect", "bearing_cage")},
    "gearbox_defect": {
        "name": "Gearbox defect report", "days": 90, "scope": "machine",
        "faults": ("gear_mesh",)},
    "fleet_health": {
        "name": "Fleet health report", "days": 30, "scope": "fleet"},
    "management_summary": {
        "name": "Management summary report", "days": 30, "scope": "fleet"},
}


def _machine(db: Session, sensor_id: UUID) -> dict[str, Any]:
    row = db.execute(text("""
        SELECT e.machine_name, e.machine_id, e.plant_name, e.area, e.line,
               e.machine_type, e.machine_criticality, e.manufacturer,
               e.model, e.rated_power_kw, e.rated_rpm,
               s.id AS sensor_id, s.mounting_location, s.mounting_method
          FROM sensor_configurations s
          LEFT JOIN equipment_masters e ON e.id = s.equipment_id
         WHERE s.id = :s
    """), {"s": str(sensor_id)}).mappings().fetchone()
    return dict(row) if row else {}


def _section(title: str, content: Any, missing_reason: str = "") -> dict:
    """One block of a report, which knows when it is empty and why."""
    empty = content in (None, [], {}, "")
    return {
        "title": title,
        "content": content,
        "present": not empty,
        # An empty section that does not say why reads as "nothing wrong".
        "reason": missing_reason if empty else "",
    }


def machine_report(
    db: Session, *, sensor_id: UUID, report_type: str = "weekly_machine_health",
) -> dict[str, Any]:
    """Section 17.1's eighteen items for one machine, over one window."""
    spec = REPORT_TYPES.get(report_type)
    if spec is None:
        raise ValueError(f"{report_type!r} is not one of section 17.2's types")

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=spec["days"])
    machine = _machine(db, sensor_id)

    health = sensor_health(db, sensor_id,
                           criticality=machine.get("machine_criticality"))
    reliability = sensor_reliability(
        db, sensor_id, criticality=machine.get("machine_criticality"))
    rul = sensor_rul(db, sensor_id)
    findings = open_findings(db, sensor_id)

    only = spec.get("faults")
    if only:
        findings = [f for f in findings if f["fault_key"] in only]

    # Anomaly: the worst score on the most recent capture in the window.
    anomaly = db.execute(text("""
        SELECT MAX(sc.score)
          FROM feature_anomaly_scores sc
          JOIN sensor_data_uploads u ON u.id = sc.upload_id
         WHERE u.sensor_id = :s AND sc.is_scored AND u.created_at >= :since
    """), {"s": str(sensor_id), "since": since}).scalar()

    symptoms = capture_symptoms(db, sensor_id)

    for finding in findings:
        finding["plots"] = plots_for(db, finding["fault_key"])

    comments = [dict(r) for r in db.execute(text("""
        SELECT verdict, note, analyst, created_at, corrected_fault_key
          FROM analyst_feedback
         WHERE sensor_id = :s AND created_at >= :since
         ORDER BY created_at DESC
    """), {"s": str(sensor_id), "since": since}).mappings().fetchall()]

    repairs = [c for c in comments if c["verdict"] == "maintenance_confirmed"]

    worst = findings[0] if findings else None
    sections = [
        _section("Asset details", machine,
                 "No equipment record is attached to this sensor."),
        _section("Measurement point", {
            "sensor_id": str(sensor_id),
            "location": machine.get("mounting_location"),
            "mounting": machine.get("mounting_method"),
        }),
        _section("Current health score", health,
                 "This machine could not be scored."),
        _section("Anomaly score",
                 round(float(anomaly), 1) if anomaly is not None else None,
                 f"No feature was scored against a baseline in the last "
                 f"{spec['days']} day(s), so how unusual this machine has "
                 f"been is unknown rather than low."),
        _section("Fault suspected",
                 worst["fault_name"] if worst else None,
                 "No rule matched. On this gateway that is usually the "
                 "spectrum being unable to separate the diagnostic "
                 "frequencies rather than the machine being well -- see the "
                 "resolution note below."),
        _section("Fault severity", worst["stage"] if worst else None,
                 "A severity describes a named fault, and none was named."),
        _section("Confidence",
                 round(float(worst["confidence"]), 3) if worst else None,
                 "Confidence is the engine's confidence in a fault it "
                 "named. With no fault there is nothing to be confident "
                 "about -- this is not confidence of zero."),
        _section("Baseline comparison", {
            "unknowns": health.get("unknowns", []),
            "data_quality": health.get("data_quality"),
            "ceiling": health.get("ceiling"),
        }),
        _section("Evidence summary",
                 [{"fault": f["fault_name"],
                   "evidence": f.get("evidence", []),
                   "against": f.get("contradicting_evidence", []),
                   "resolution": f.get("resolution")}
                  for f in findings],
                 "There is no evidence to summarise because no fault was "
                 "named."),
        _section("Symptom observations", symptoms.get("channels", []),
                 symptoms.get("reason", "")),
        _section("Recommended plots",
                 {f["fault_key"]: f["plots"] for f in findings},
                 "Plot guidance is per named fault, and none was named."),
        _section("Recommended action",
                 worst.get("recommended_action") if worst else None,
                 "No action is recommended because no fault was named. That "
                 "is not the same as no action being needed."),
        _section("Analyst comments", comments,
                 f"No analyst has commented on this machine in the last "
                 f"{spec['days']} day(s)."),
        _section("Maintenance feedback", repairs,
                 "No repair has been confirmed in this period."),
        _section("Reliability", reliability),
        _section("RUL", rul if rul.get("available") else None,
                 rul.get("reason", "")),
    ]

    absent = [s["title"] for s in sections if not s["present"]]
    # An empty section with no reason is exactly the silent omission this
    # module exists to avoid, so it is caught here rather than on a screen.
    silent = [s["title"] for s in sections if not s["present"]
              and not s["reason"]]
    if silent:
        logger.error("Report sections empty with no reason given: %s", silent)

    return {
        "report_type": report_type,
        "sections_without_a_reason": silent,
        "name": spec["name"],
        "scope": "machine",
        "sensor_id": str(sensor_id),
        "machine_name": machine.get("machine_name"),
        "period_days": spec["days"],
        "period_start": since,
        "generated_at": now,
        "sections": sections,
        "sections_absent": absent,
        "governance": governance_summary(db)["components"],
        "reason": (
            f"{len(sections) - len(absent)} of {len(sections)} sections have "
            f"content."
            + (f" {len(absent)} could not be filled and each says why rather "
               f"than being left out: {', '.join(absent)}." if absent else "")),
    }


def fleet_report(
    db: Session, *, report_type: str = "fleet_health",
    plant_name: Optional[str] = None,
) -> dict[str, Any]:
    """The fleet-scoped types in section 17.2."""
    spec = REPORT_TYPES.get(report_type)
    if spec is None:
        raise ValueError(f"{report_type!r} is not one of section 17.2's types")

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=spec["days"])
    site = fleet(db, plant_name=plant_name)

    alarms = [dict(r) for r in db.execute(text("""
        SELECT s.id AS sensor_id, e.machine_name, a.channel, a.feature_code,
               a.band, a.score, a.escalating, a.first_alarmed_at, a.reason
          FROM feature_alarm_state a
          JOIN sensor_configurations s ON s.id = a.sensor_id
          LEFT JOIN equipment_masters e ON e.id = s.equipment_id
         WHERE a.alarming
         ORDER BY a.escalating DESC, a.score DESC NULLS LAST
    """)).mappings().fetchall()]

    if report_type == "critical_alarms":
        alarms = [a for a in alarms if a["band"] in ("critical", "high")]

    sections = [
        _section("Site health", site["site_health_score"],
                 "No machine on this site could be scored."),
        _section("Fleet reliability", site["site_reliability_score"],
                 "No machine has a long enough record to judge."),
        _section("Most at risk", site["most_at_risk"],
                 "Nothing could be ranked."),
        _section("Alarms", alarms,
                 f"Nothing is ringing. On this gateway that is not "
                 f"necessarily good news -- the escalation path needs a "
                 f"steadiness check the capture length cannot support."),
        _section("Open findings", site["counts"]["open_findings"]),
        _section("Machines under watch", site["counts"]["under_watch"]),
        _section("False alarm reduction", site["feedback"],
                 site["feedback"]["reason"]),
        _section("Maintenance action status", site["maintenance"]),
        _section("Machines that could not be scored",
                 site["unmeasured_machines"],
                 "Every machine on this site could be scored."),
    ]
    absent = [s["title"] for s in sections if not s["present"]]

    return {
        "report_type": report_type, "name": spec["name"], "scope": "fleet",
        "plant_name": plant_name, "period_days": spec["days"],
        "period_start": since, "generated_at": now,
        "sections": sections, "sections_absent": absent,
        "counts": site["counts"],
        "governance": governance_summary(db)["components"],
        "reason": site["reason"],
    }


def available_reports() -> list[dict[str, Any]]:
    """Section 17.2's nine types, with what each covers."""
    return [{"key": key, "name": spec["name"], "scope": spec["scope"],
             "period_days": spec["days"],
             "faults": list(spec.get("faults", ()))}
            for key, spec in REPORT_TYPES.items()]
