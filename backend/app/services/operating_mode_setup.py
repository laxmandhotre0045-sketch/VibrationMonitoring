"""Where a machine's operating bands come from — VIK-039 setup.

The mode detector refuses to guess what load a machine was under, so until
bands exist every capture is unknown and per-mode baselines do nothing. The
obvious reading is that somebody must now sit down and characterise every
machine. For most of them they must. For a fixed-speed machine they need
not, because the numbers are already on the equipment record.

`operating_speed_min` and `operating_speed_max` are what a person entered
when they registered the machine -- on this pump, 1440 to 1500 rpm against a
nameplate of 1480. That is a band. Deriving one mode from it is not
guessing; it is reading a field somebody already filled in.

**One band, and only one.** This does not invent low/medium/high load by
slicing the operating range into thirds. Those are different *loads*, not
different speeds, and a fixed-speed pump running at 1480 rpm at part load
and full load sits in the same third either way. Splitting the range would
produce three bands that are all the same operating state wearing different
labels, and three baselines each built from a third of the data for no
reason. A machine that genuinely has load states needs somebody to say what
they are, and this says so rather than pretending.

So: a single `normal_running` band for machines whose speed range is known,
and nothing at all for machines whose is not.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.operating_mode import ModeBand

logger = logging.getLogger(__name__)

TABLE = "operating_modes"

#: How far outside the recorded operating range a capture may sit and still
#: count as the same running state.
#:
#: The range on the equipment record is what the machine is specified to do,
#: not what it was measured doing, and a fixed-speed motor drifts with load
#: and supply frequency. Five percent of 1480 rpm is 74 -- wider than the
#: 60 rpm the record itself spans, which is the point: a capture at 1435
#: rpm on a pump specified 1440 to 1500 is the same machine doing the same
#: thing, and sending it to unknown would exclude it from its own baseline.
RANGE_MARGIN = 0.05

#: Used when the record gives a nameplate but no range at all. A fixed-speed
#: machine holds its rated speed within a few percent; ten is generous
#: enough to cover slip and supply variation without swallowing a genuine
#: second operating state.
NAMEPLATE_MARGIN = 0.10


def propose_band(rated_rpm: Optional[float],
                 speed_min: Optional[float],
                 speed_max: Optional[float]) -> Optional[dict[str, Any]]:
    """The one band an equipment record justifies, or None.

    None is the common answer for a machine nobody has characterised, and it
    is the right one: the detector then reports unknown with a reason, which
    is honest, rather than banding against a number nobody supplied.
    """
    if speed_min and speed_max and speed_max >= speed_min:
        # A recorded range. Trusted, widened by the margin.
        low = float(speed_min) * (1 - RANGE_MARGIN)
        high = float(speed_max) * (1 + RANGE_MARGIN)
        basis = (f"the operating range on the equipment record "
                 f"({speed_min:g}-{speed_max:g} rpm), widened by "
                 f"{RANGE_MARGIN:.0%} for slip and supply variation")
    elif rated_rpm:
        low = float(rated_rpm) * (1 - NAMEPLATE_MARGIN)
        high = float(rated_rpm) * (1 + NAMEPLATE_MARGIN)
        basis = (f"the nameplate speed ({rated_rpm:g} rpm) plus or minus "
                 f"{NAMEPLATE_MARGIN:.0%}, because no operating range is "
                 f"recorded")
    else:
        return None

    # A range that cannot be a speed is a data-entry problem, not a band.
    # One equipment row here holds 55-85 against a nameplate of 1480, which
    # looks like Hz written into an rpm column; banding on it would send
    # every capture to unknown while looking configured.
    if rated_rpm and not (low <= float(rated_rpm) <= high):
        logger.warning(
            "Equipment rated at %s rpm has an operating range of %s-%s, "
            "which does not contain it. No band proposed.",
            rated_rpm, speed_min, speed_max)
        return None
    if low <= 0 or high <= low:
        return None

    return {
        "label": "normal_running",
        "rpm_min": round(low, 1),
        "rpm_max": round(high, 1),
        "source": "configured",
        "notes": (f"Derived from {basis}. This machine is treated as having "
                  f"one running state. If it genuinely runs at distinct "
                  f"loads, those bands have to be entered by someone who "
                  f"knows the machine -- slicing a speed range into thirds "
                  f"would produce three labels for one operating state."),
    }


def ensure_modes_for_equipment(db: Session, equipment_id: UUID) -> dict[str, Any]:
    """Create the derived band for one machine, if it has none.

    Never overwrites. A band somebody configured deliberately outranks
    anything derived from a record, and this running twice must not undo a
    correction made between the two.
    """
    existing = db.execute(text(
        f"SELECT COUNT(*) FROM {TABLE} WHERE equipment_id = :e"),
        {"e": str(equipment_id)}).scalar()
    if existing:
        return {"equipment_id": str(equipment_id), "created": 0,
                "reason": f"{existing} mode(s) already defined; left alone"}

    row = db.execute(text("""
        SELECT machine_name, rated_rpm, operating_speed_min, operating_speed_max
          FROM equipment_masters WHERE id = :e
    """), {"e": str(equipment_id)}).fetchone()
    if row is None:
        return {"equipment_id": str(equipment_id), "created": 0,
                "reason": "no such equipment"}

    band = propose_band(row.rated_rpm, row.operating_speed_min,
                        row.operating_speed_max)
    if band is None:
        return {"equipment_id": str(equipment_id), "created": 0,
                "machine": row.machine_name,
                "reason": ("no usable speed information on the equipment "
                           "record, so every capture stays unknown until "
                           "somebody defines the bands")}

    db.execute(text(f"""
        INSERT INTO {TABLE}
            (equipment_id, label, rpm_min, rpm_max, source, notes)
        VALUES (:e, :label, :rpm_min, :rpm_max, :source, :notes)
    """), {"e": str(equipment_id), **band})

    logger.info("Created %s band %.0f-%.0f rpm for %s",
                band["label"], band["rpm_min"], band["rpm_max"],
                row.machine_name)
    return {"equipment_id": str(equipment_id), "created": 1,
            "machine": row.machine_name, "band": band}


def load_bands(db: Session, equipment_id: UUID) -> list[ModeBand]:
    """The active bands for one machine, ready for the detector."""
    rows = db.execute(text(f"""
        SELECT id, label, rpm_min, rpm_max, load_min, load_max, source
          FROM {TABLE} WHERE equipment_id = :e AND is_active
         ORDER BY rpm_min NULLS FIRST
    """), {"e": str(equipment_id)}).mappings().fetchall()
    return [ModeBand(
        id=str(r["id"]), label=r["label"],
        rpm_min=float(r["rpm_min"]) if r["rpm_min"] is not None else None,
        rpm_max=float(r["rpm_max"]) if r["rpm_max"] is not None else None,
        load_min=float(r["load_min"]) if r["load_min"] is not None else None,
        load_max=float(r["load_max"]) if r["load_max"] is not None else None,
        source=r["source"],
    ) for r in rows]
