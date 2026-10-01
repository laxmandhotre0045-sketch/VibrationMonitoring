"""Health scores on the fleet summary — VIK-055's last mile.

`app.crud.dashboard` builds the summary and leaves the health fields empty.
It has to: scoring a machine needs the fault, alarm and baseline services,
and crud is not allowed to import those. The architecture test says so and
it caught the first version of this, which had the import sitting in crud.

So the composition happens here and the router layers it on.

**The worst sensor, not the average.** A machine with one failing bearing
and three quiet channels is a machine with a failing bearing. Averaging is
how that disappears, and it disappears most on exactly the machines with
the most sensors.

**A machine that cannot be scored keeps a null score.** Not 100, not the
fleet average, not the last known value. The old lookup gave every machine
a number whatever was behind it, and a dashboard cell that is never empty
is a dashboard nobody checks.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.health_storage import sensor_health

logger = logging.getLogger(__name__)

#: Said on a machine that has sensors and captures but nothing scoreable.
NOT_SCOREABLE = (
    "Nothing measured on this machine could be scored, so it has no health "
    "figure. An unscored machine is not a healthy one -- the difference is "
    "the only thing an empty cell here can usefully mean.")

NO_SENSORS = (
    "No sensor is attached to this machine, so there is nothing to score.")


def _sensors_for(db: Session, equipment_id: UUID) -> list[UUID]:
    return [row[0] for row in db.execute(text(
        "SELECT id FROM sensor_configurations WHERE equipment_id = :e"),
        {"e": str(equipment_id)}).fetchall()]


def worst_sensor_health(
    db: Session, equipment_id: UUID, criticality: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """The lowest-scoring sensor on this machine, or None if none scored."""
    scored = []
    for sensor_id in _sensors_for(db, equipment_id):
        try:
            verdict = sensor_health(db, sensor_id, criticality=criticality)
        except Exception:
            # One unscoreable sensor must not take the dashboard down with
            # it. The machine keeps a null score and says so.
            logger.exception("Health scoring failed for sensor %s", sensor_id)
            continue
        if verdict.get("score") is not None:
            scored.append(verdict)
    return min(scored, key=lambda v: v["score"]) if scored else None


def attach_health(db: Session, summary: dict[str, Any]) -> dict[str, Any]:
    """Fill in each machine's health, and the fleet average, in place."""
    scores: list[float] = []

    for machine in summary.get("equipment_health") or []:
        equipment_id = machine.get("equipment_id")
        if not equipment_id:
            continue

        if not _sensors_for(db, equipment_id):
            machine["health_reason"] = machine.get("health_reason") or NO_SENSORS
            continue

        verdict = worst_sensor_health(
            db, equipment_id, machine.get("machine_criticality"))
        if verdict is None:
            machine["health_reason"] = machine.get("health_reason") or NOT_SCOREABLE
            continue

        machine.update({
            "health_score": verdict["score"],
            "health_band": verdict["band"],
            "health_reason": verdict["reason"],
            "health_ceiling": verdict["ceiling"],
            "data_quality": verdict["data_quality"],
        })
        scores.append(verdict["score"])

    counts = summary.get("counts")
    if isinstance(counts, dict):
        # None rather than 0 for an empty fleet: an average of nothing is
        # not zero health, and 0 renders as a plant in crisis.
        counts["average_health_score"] = (
            round(sum(scores) / len(scores), 1) if scores else None)
    return summary
