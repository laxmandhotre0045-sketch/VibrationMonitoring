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


#: Section 6.1 lists low, medium and high load as modes. They can only
#: exist if somebody configured a band called that, and "medium load" never
#: was -- so it was unreachable rather than undetected.
#:
#: These are derived from the machine's own recorded load range rather than
#: invented: the plant already told us the range, and thirds of a stated
#: range is a defensible reading of it. A machine with no load range gets
#: no load bands, which is the same rule as everywhere else -- the engine
#: does not manufacture the one thing it was not given.
LOAD_BAND_LABELS = ("low_load", "medium_load", "high_load")


def derive_load_bands(db, equipment_id) -> list[dict]:
    """Thirds of the machine's stated load range, as bands.

    Returns an empty list when the range is unknown or degenerate. A
    machine that runs at one load has one mode, and splitting that into
    three would put nearly identical captures into three baselines and make
    each of them thinner.
    """
    from sqlalchemy import text

    row = db.execute(text("""
        SELECT load_range_min, load_range_max, rated_rpm
          FROM equipment_masters WHERE id = :e
    """), {"e": str(equipment_id)}).fetchone()
    if row is None or row[0] is None or row[1] is None:
        return []

    low, high = float(row[0]), float(row[1])
    if high <= low:
        return []

    step = (high - low) / 3.0
    bands = []
    for index, label in enumerate(LOAD_BAND_LABELS):
        bands.append({
            "label": label,
            "load_min": round(low + step * index, 3),
            "load_max": round(low + step * (index + 1), 3),
            "source": "derived",
            "notes": (
                f"Derived as a third of this machine's stated load range "
                f"{low:g}-{high:g}. Not measured from its behaviour -- if "
                f"the machine actually runs in two clusters rather than "
                f"three even bands, mode discovery will say so."),
        })
    return bands


#: Captures needed before mode discovery is worth running. Below this the
#: clusters are describing scatter.
DISCOVERY_MIN_CAPTURES = 60

#: Most modes discovery will propose. More than four bands on one machine
#: is almost always the clustering finding structure in noise.
DISCOVERY_MAX_MODES = 4


def discover_modes(db, sensor_id, max_modes: int = DISCOVERY_MAX_MODES):
    """Section 11.2's "clustering for mode discovery".

    Proposes bands for a machine nobody has configured, from how it has
    actually been running. Deliberately the last resort and never automatic:
    the module docstring for `app.ai.operating_mode` says banding beats
    clustering because a band a plant engineer writes down encodes what the
    machine is *for*, and a cluster only encodes what it has been doing --
    including, if it has been running badly, the fault.

    So this returns *proposals* with the evidence behind them for somebody
    to accept or reject. Writing them straight into the bands table would
    let a machine that has spent a month degrading acquire a mode called
    "normal" that is anything but.
    """
    from sqlalchemy import text

    rows = db.execute(text("""
        SELECT m.shaft_hz, m.overall_level
          FROM capture_operating_modes m
          JOIN sensor_data_uploads u ON u.id = m.upload_id
         WHERE u.sensor_id = :s AND m.shaft_hz IS NOT NULL
           AND m.overall_level IS NOT NULL
    """), {"s": str(sensor_id)}).fetchall()

    points = [(float(a), float(b)) for a, b in rows if a and b]
    if len(points) < DISCOVERY_MIN_CAPTURES:
        return {
            "proposed": [], "captures": len(points),
            "reason": (
                f"Mode discovery needs about {DISCOVERY_MIN_CAPTURES} "
                f"captures and this machine has {len(points)}. Below that "
                f"the clusters describe scatter, and a proposed band built "
                f"from scatter is worse than no band -- somebody would "
                f"accept it."),
        }

    try:
        import numpy as np
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler
    except Exception:
        return {"proposed": [], "captures": len(points),
                "reason": "Clustering is unavailable in this environment."}

    data = np.asarray(points, dtype=float)
    # Scaled, because shaft speed is tens and level is thousandths --
    # unscaled, the clustering would be entirely about speed and the level
    # axis would contribute nothing.
    scaled = StandardScaler().fit_transform(data)

    best = None
    for k in range(2, min(max_modes, len(points) // 20) + 1):
        model = KMeans(n_clusters=k, n_init=10, random_state=20260930)
        labels = model.fit_predict(scaled)
        # Separation against spread: a split worth proposing puts the
        # clusters further apart than the points within them are.
        spread = float(np.mean([
            np.linalg.norm(scaled[labels == i]
                           - model.cluster_centers_[i], axis=1).mean()
            for i in range(k) if (labels == i).any()]))
        gaps = [np.linalg.norm(model.cluster_centers_[i]
                               - model.cluster_centers_[j])
                for i in range(k) for j in range(i + 1, k)]
        separation = float(min(gaps)) if gaps else 0.0
        score = separation / spread if spread > 0 else 0.0
        if best is None or score > best["score"]:
            best = {"k": k, "labels": labels, "score": score}

    if best is None or best["score"] < 1.5:
        return {
            "proposed": [], "captures": len(points),
            "reason": (
                "This machine's captures do not separate into distinct "
                "operating points -- the clusters sit closer together than "
                "the spread within them. One mode is the honest reading."),
        }

    proposed = []
    for index in range(best["k"]):
        member = data[best["labels"] == index]
        if not len(member):
            continue
        rpm = member[:, 0] * 60.0
        proposed.append({
            "label": f"discovered_{index + 1}",
            "rpm_min": round(float(np.percentile(rpm, 5)), 1),
            "rpm_max": round(float(np.percentile(rpm, 95)), 1),
            "captures": int(len(member)),
            "median_level_g": round(float(np.median(member[:, 1])), 6),
            "source": "discovered",
        })

    proposed.sort(key=lambda b: b["rpm_min"])
    return {
        "proposed": proposed, "captures": len(points),
        "separation": round(best["score"], 2),
        "reason": (
            f"{best['k']} operating points found across {len(points)} "
            f"captures, separated by {best['score']:.1f} times their own "
            f"spread. These are proposals from how the machine has been "
            f"running, not from what it is for -- review them before "
            f"accepting. A machine that has spent the period degrading "
            f"will offer you a cluster that looks like a mode."),
    }
