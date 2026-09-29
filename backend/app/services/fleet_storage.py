"""The plant as one picture — section 19.3, and fleet-level intelligence.

Everything so far answers questions about one machine. This answers the
ones a plant manager asks: which ten need attention, how is the site as a
whole, and is the platform earning its keep.

**A fleet average is only honest if it says what it left out.** Machines
that cannot be scored are excluded rather than counted as healthy, and the
count of those travels with the average. A site of twenty machines where
eleven have never been measured has a fleet health score computed from
nine, and a number that does not say so is worse than no number.

**"False alarm reduction" is the one figure here the platform must not
flatter itself on.** Section 19.3 asks for it, and the honest version is
the ratio of analyst rejections to total verdicts -- which gets *worse*
when the platform is wrong. Reporting a number that only ever improves
would make the whole feedback loop decorative.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.feedback import NEGATIVE, POSITIVE
from app.services.health_storage import sensor_health, sensor_reliability

logger = logging.getLogger(__name__)

FINDINGS = "fault_findings"
ALARMS = "feature_alarm_state"
FEEDBACK = "analyst_feedback"

#: How many machines the "most at risk" list holds. Section 19.3 says ten.
TOP_N = 10


def _machines(db: Session) -> list[dict[str, Any]]:
    return [dict(r) for r in db.execute(text("""
        SELECT e.id AS equipment_id, e.machine_name, e.plant_name, e.area,
               e.machine_criticality, e.last_maintenance_date,
               s.id AS sensor_id
          FROM equipment_masters e
          LEFT JOIN sensor_configurations s ON s.equipment_id = e.id
         ORDER BY e.machine_name
    """)).mappings().fetchall()]


def fleet(db: Session, *, plant_name: Optional[str] = None) -> dict[str, Any]:
    """The whole site, summarised. Section 19.3's management view."""
    rows = _machines(db)
    if plant_name:
        rows = [r for r in rows
                if (r["plant_name"] or "").lower() == plant_name.lower()]

    machines: list[dict[str, Any]] = []
    unmeasured: list[str] = []

    for row in rows:
        entry = {
            "equipment_id": str(row["equipment_id"]),
            "machine_name": row["machine_name"],
            "plant_name": row["plant_name"], "area": row["area"],
            "criticality": row["machine_criticality"],
            "sensor_id": str(row["sensor_id"]) if row["sensor_id"] else None,
            "health": None, "health_band": "unknown",
            "reliability": None, "reliability_band": "unknown",
            "open_findings": 0, "worst_stage": None, "reason": "",
        }

        if not row["sensor_id"]:
            entry["reason"] = ("No sensor is attached to this machine, so "
                               "nothing is known about it.")
            unmeasured.append(row["machine_name"])
            machines.append(entry)
            continue

        try:
            health = sensor_health(
                db, row["sensor_id"],
                criticality=row["machine_criticality"])
            reliability = sensor_reliability(
                db, row["sensor_id"],
                criticality=row["machine_criticality"],
                last_maintenance=row["last_maintenance_date"])
        except Exception:
            logger.exception("Fleet summary failed for %s", row["sensor_id"])
            entry["reason"] = "This machine could not be scored."
            unmeasured.append(row["machine_name"])
            machines.append(entry)
            continue

        entry.update({
            "health": health.get("score"),
            "health_band": health.get("band", "unknown"),
            "health_ceiling": health.get("ceiling"),
            "data_quality": health.get("data_quality"),
            "reliability": reliability.get("score"),
            "reliability_band": reliability.get("band", "unknown"),
            "reliability_proven": reliability.get("proven"),
            "open_findings": health.get("open_findings", 0),
            "reason": health.get("reason", ""),
        })
        if health.get("score") is None:
            unmeasured.append(row["machine_name"])
        machines.append(entry)

    scored = [m for m in machines if m["health"] is not None]
    dependable = [m for m in machines if m["reliability"] is not None]

    site_health = (round(sum(m["health"] for m in scored) / len(scored), 1)
                   if scored else None)
    site_reliability = (
        round(sum(m["reliability"] for m in dependable) / len(dependable), 1)
        if dependable else None)

    # Most at risk: worst health first, and a machine nobody can score is
    # not "fine" -- it simply cannot be ranked, so it is listed separately.
    at_risk = sorted(scored, key=lambda m: m["health"])[:TOP_N]

    critical_alarms = db.execute(text(f"""
        SELECT COUNT(*) FROM {ALARMS}
         WHERE alarming AND band IN ('critical', 'high')
    """)).scalar() or 0
    open_findings = db.execute(text(f"""
        SELECT COUNT(*) FROM {FINDINGS} WHERE resolved_at IS NULL
    """)).scalar() or 0
    under_watch = sum(
        1 for m in scored
        if m["health_band"] in ("Watch", "Poor", "High risk", "Critical"))

    return {
        "plant_name": plant_name,
        "machines": machines,
        "most_at_risk": at_risk,
        "counts": {
            "machines": len(machines),
            "scored": len(scored),
            "unmeasured": len(unmeasured),
            "critical_alarms": int(critical_alarms),
            "open_findings": int(open_findings),
            "under_watch": under_watch,
        },
        "site_health_score": site_health,
        "site_reliability_score": site_reliability,
        "unmeasured_machines": unmeasured,
        "feedback": alarm_quality(db),
        "maintenance": maintenance_status(db),
        "reason": (
            f"{len(scored)} of {len(machines)} machine(s) could be scored."
            + (f" {len(unmeasured)} could not and are excluded from the site "
               f"averages rather than counted as healthy: "
               f"{', '.join(unmeasured[:4])}"
               f"{'...' if len(unmeasured) > 4 else ''}."
               if unmeasured else "")),
    }


def alarm_quality(db: Session) -> dict[str, Any]:
    """Section 19.3's "false alarm reduction", stated honestly.

    This is the one number on the management view that the platform must
    not be able to flatter itself on: it is the share of analyst verdicts
    that rejected a finding, so it rises when the platform is wrong. A
    metric that only ever improves would make the feedback loop decorative.
    """
    rows = {r[0]: r[1] for r in db.execute(text(f"""
        SELECT verdict, COUNT(*) FROM {FEEDBACK} GROUP BY verdict
    """)).fetchall()}

    rejected = sum(rows.get(v, 0) for v in NEGATIVE)
    confirmed = sum(rows.get(v, 0) for v in POSITIVE)
    judged = rejected + confirmed

    if not judged:
        return {
            "judged": 0, "confirmed": 0, "rejected": 0,
            "false_alarm_rate": None, "trend": None,
            "reason": ("No analyst has confirmed or rejected a finding yet, "
                       "so how often the platform is right is unknown -- not "
                       "good."),
        }

    rate = rejected / judged

    # Whether it is improving: the most recent half against the earlier.
    # The verdict lists are module constants, not user input, so they are
    # inlined -- a bound tuple would need expanding=True and buys nothing.
    _negative = ", ".join(f"'{v}'" for v in NEGATIVE)
    _judged = ", ".join(f"'{v}'" for v in (*NEGATIVE, *POSITIVE))
    recent = db.execute(text(f"""
        WITH ordered AS (
            SELECT verdict,
                   ROW_NUMBER() OVER (ORDER BY created_at) AS n,
                   COUNT(*) OVER () AS total
              FROM {FEEDBACK}
             WHERE verdict IN ({_judged})
        )
        SELECT
          AVG(CASE WHEN n <= total / 2.0
                   THEN CASE WHEN verdict IN ({_negative})
                             THEN 1.0 ELSE 0.0 END END),
          AVG(CASE WHEN n > total / 2.0
                   THEN CASE WHEN verdict IN ({_negative})
                             THEN 1.0 ELSE 0.0 END END)
          FROM ordered
    """)).fetchone()

    trend = None
    if recent and recent[0] is not None and recent[1] is not None:
        change = float(recent[1]) - float(recent[0])
        trend = ("improving" if change < -0.05 else
                 "worsening" if change > 0.05 else "flat")

    return {
        "judged": judged, "confirmed": confirmed, "rejected": rejected,
        "false_alarm_rate": round(rate, 3),
        "trend": trend,
        "reason": (
            f"Analysts have judged {judged} finding(s): {confirmed} correct "
            f"and {rejected} rejected, a false-alarm rate of {rate:.0%}"
            + (f", {trend} against the earlier half of the record."
               if trend else ". Too few to say whether that is improving.")),
    }


def maintenance_status(db: Session) -> dict[str, Any]:
    """Section 19.3's "maintenance action status": what is being worked on."""
    rows = {r[0]: r[1] for r in db.execute(text(f"""
        SELECT triage_status, COUNT(*) FROM {FINDINGS}
         WHERE resolved_at IS NULL GROUP BY triage_status
    """)).fetchall()}
    confirmed = db.execute(text(f"""
        SELECT COUNT(*) FROM {FEEDBACK} WHERE verdict = 'maintenance_confirmed'
    """)).scalar() or 0
    unassigned = rows.get("new", 0)

    return {
        "by_status": rows,
        "unassigned": unassigned,
        "repairs_confirmed": int(confirmed),
        "reason": (
            f"{sum(rows.values())} open finding(s): {unassigned} not yet "
            f"assigned to anyone."
            if rows else "Nothing is currently open."),
    }
