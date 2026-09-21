"""Resolve a machine's bearings against the catalogue — VIK-010.

Equipment Master stores whatever the plant wrote on the record: "6312-C3",
"6310 C3", "NU 2220 E". The catalogue stores a bare designation, "6312". The
job here is to get from one to the other without either inventing a match or
refusing a real one.

Three rules, and the third is the one that matters:

**Strip only what is provably a suffix.** Clearance codes, seal and shield
codes and cage codes describe how a bearing is built, not its internal
geometry, so they do not change the fault orders. The base number does. So the
suffixes below are removed by an explicit list rather than by a general
"trailing letters" rule -- "NU2220" and "N2220" are different bearings, and a
rule loose enough to reach the first would happily turn one into the other.

**A miss is not a failure.** Where nothing matches, the existing estimator
still answers, and its lower confidence travels with the answer. The ticket is
explicit: fall back and keep the lower confidence rather than failing. A
machine with an uncatalogued bearing should still get a diagnosis, clearly
marked as estimated.

**Disagreement between manufacturers is reported, not averaged.** The same
designation from two makers can carry slightly different orders -- 6310 reads
BPFO 3.0480 from one and 3.0470 from another. Averaging those produces a
number no manufacturer publishes. The first is used and the spread is recorded,
so a downstream reader can see the catalogue was not unanimous.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

#: Suffixes that describe construction rather than geometry, so removing them
#: is safe. Ordered longest-first so "2RS1" is consumed before "2RS".
#:
#: Deliberately a closed list. A general rule like "strip trailing letters"
#: would turn NU2220 into 2220 and N2220 into 2220 as well -- three different
#: bearings collapsing onto one catalogue row, each with the wrong fault
#: orders, and nothing on screen to say so.
_SUFFIXES = (
    "2RS1", "2RSR", "2RS", "2ZR", "2Z", "RS1", "RSR", "RS", "ZZ", "Z",
    "C2", "C3", "C4", "C5", "CM", "CN",
    "M", "MA", "MB", "CA", "CC", "CD", "E1", "E",
    "TVH", "TVP", "TN9", "TN", "P5", "P6", "P63",
    "K", "J", "G", "H", "V", "W33", "W",
)

#: Separators a plant might use between the base number and a suffix.
_SEPARATOR = re.compile(r"[\s/_.\-]+")

#: How far two manufacturers' orders may differ before the match is flagged as
#: not unanimous. 1% is well inside the published rounding (3.048 vs 3.047 is
#: 0.03%) and well below any difference that would change a diagnosis.
_AGREEMENT_TOLERANCE = 0.01


@dataclass
class BearingMatch:
    """What the catalogue could tell us about one bearing."""
    query: str
    normalised: str
    #: The catalogue's own integer Bearing ID (source_bearing_id), not the
    #: table's UUID primary key. equipment_masters.bearing_*_catalog_id is an
    #: integer column, so the UUID cannot go there -- and the spreadsheet's own
    #: id is the stabler reference anyway, surviving a reload of the table.
    catalog_id: Optional[int] = None
    manufacturer: Optional[str] = None
    designation: Optional[str] = None
    rolling_elements: Optional[int] = None
    ftf: Optional[float] = None
    bsf: Optional[float] = None
    bpfo: Optional[float] = None
    bpfi: Optional[float] = None
    #: "catalogue" when the numbers are published, "estimated" when they come
    #: from the geometry estimator, "none" when neither could answer.
    source: str = "none"
    #: 1.0 for an unambiguous catalogue hit, lower for an estimate or a
    #: catalogue that was not unanimous.
    confidence: float = 0.0
    #: How many catalogue rows carried this designation.
    candidates: int = 0
    #: Set when manufacturers disagreed, naming the spread.
    notes: list[str] = field(default_factory=list)


def normalise_designation(raw: str) -> str:
    """Reduce a plant's bearing number to the catalogue's base designation.

    "6312-C3" -> "6312", "6310 C3" -> "6310", "NU 2220 E" -> "NU2220".

    Separators go first, then one suffix from the closed list above, and only
    if what remains still contains a digit -- stripping "E" off "E" would leave
    nothing, and a bearing number with no digits is not a bearing number.
    """
    if not raw:
        return ""
    text_value = _SEPARATOR.sub("", str(raw).strip().upper())
    if not text_value:
        return ""

    # One suffix only. "6312-C3-2RS" is not a designation anyone writes, and
    # stripping repeatedly risks eating into the base number.
    for suffix in _SUFFIXES:
        if text_value.endswith(suffix) and len(text_value) > len(suffix):
            candidate = text_value[: -len(suffix)]
            if any(ch.isdigit() for ch in candidate):
                return candidate
    return text_value


def _rows_for(db: Session, designation: str) -> list[Any]:
    return db.execute(text("""
        SELECT source_bearing_id, manufacturer, designation, rolling_elements,
               ftf, bsf, bpfo, bpfi, is_consistent
          FROM bearing_fault_frequencies
         WHERE designation = :d AND is_consistent = true
         ORDER BY manufacturer
    """), {"d": designation}).fetchall()


def _spread(values: list[float]) -> float:
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return 0.0
    low, high = min(clean), max(clean)
    return (high - low) / high if high else 0.0


def match_from_catalogue(db: Session, raw: str,
                         preferred_manufacturer: Optional[str] = None) -> BearingMatch:
    """Look one bearing up. Never raises; a miss returns source="none"."""
    normalised = normalise_designation(raw)
    result = BearingMatch(query=str(raw or ""), normalised=normalised)
    if not normalised:
        return result

    rows = _rows_for(db, normalised)
    result.candidates = len(rows)
    if not rows:
        return result

    chosen = rows[0]
    if preferred_manufacturer:
        wanted = preferred_manufacturer.strip().upper()
        for row in rows:
            if (row.manufacturer or "").strip().upper() == wanted:
                chosen = row
                break

    # Report disagreement rather than averaging it away.
    confidence = 1.0
    for name in ("ftf", "bsf", "bpfo", "bpfi"):
        spread = _spread([float(getattr(r, name)) for r in rows
                          if getattr(r, name) is not None])
        if spread > _AGREEMENT_TOLERANCE:
            confidence = 0.85
            result.notes.append(
                f"{len(rows)} manufacturers list {normalised} and their "
                f"{name.upper()} differs by {spread * 100:.1f}%; "
                f"{chosen.manufacturer} is used."
            )

    result.catalog_id = chosen.source_bearing_id
    result.manufacturer = chosen.manufacturer
    result.designation = chosen.designation
    result.rolling_elements = chosen.rolling_elements
    result.ftf = float(chosen.ftf) if chosen.ftf is not None else None
    result.bsf = float(chosen.bsf) if chosen.bsf is not None else None
    result.bpfo = float(chosen.bpfo) if chosen.bpfo is not None else None
    result.bpfi = float(chosen.bpfi) if chosen.bpfi is not None else None
    result.source = "catalogue"
    result.confidence = confidence
    return result


def match_with_fallback(db: Session, raw: str,
                        preferred_manufacturer: Optional[str] = None) -> BearingMatch:
    """Catalogue first, then the geometry estimator.

    The estimator only handles deep-groove ball bearings and warns that its
    element count may be out by one. That warning is the reason its confidence
    stays low here rather than being rounded up to look decisive.
    """
    result = match_from_catalogue(db, raw, preferred_manufacturer)
    if result.source == "catalogue" or not result.normalised:
        return result

    try:
        from app.ai.bearing_estimator import estimate_orders
    except ImportError:
        # The estimator lives in vibrationbot until VIK-035 moves it into the
        # shared package. Its absence is not an error: no estimate simply means
        # the bearing is unresolved, which is already this result's state.
        result.notes.append(
            "Not in the catalogue, and the geometry estimator is not available "
            "in the backend yet (VIK-035)."
        )
        return result

    estimate = estimate_orders(result.normalised)
    if not estimate:
        result.notes.append(f"{result.normalised} is not in the catalogue and "
                            f"could not be estimated.")
        return result

    result.source = "estimated"
    result.confidence = estimate.get("confidence", 0.6)
    result.rolling_elements = estimate.get("rolling_elements")
    result.ftf = estimate.get("ftf")
    result.bsf = estimate.get("bsf")
    result.bpfo = estimate.get("bpfo")
    result.bpfi = estimate.get("bpfi")
    result.notes.append(
        "Estimated from boundary dimensions, not published. The element count "
        "may be out by one, which shifts every order."
    )
    return result


def resolve_equipment(db: Session, equipment_id: UUID,
                      commit: bool = True) -> dict[str, Any]:
    """Resolve both bearings on one machine and store the catalogue ids.

    Writes only the catalogue ids. `bearing_database_mapped` is left alone:
    Laxman's readiness check already treats a resolved catalogue id as
    satisfying it, so the flag stops being a box anyone can tick without
    this code having to write to it.
    """
    row = db.execute(text("""
        SELECT id, machine_name, bearing_number_de, bearing_number_nde
          FROM equipment_masters WHERE id = :eid
    """), {"eid": str(equipment_id)}).fetchone()
    if not row:
        return {"equipment_id": str(equipment_id), "found": False}

    de = match_with_fallback(db, row.bearing_number_de or "")
    nde = match_with_fallback(db, row.bearing_number_nde or "")

    db.execute(text("""
        UPDATE equipment_masters
           SET bearing_de_catalog_id = :de, bearing_nde_catalog_id = :nde
         WHERE id = :eid
    """), {"de": de.catalog_id, "nde": nde.catalog_id, "eid": str(equipment_id)})
    if commit:
        db.commit()

    return {
        "equipment_id": str(equipment_id),
        "machine_name": row.machine_name,
        "found": True,
        "de": de,
        "nde": nde,
    }


def resolve_all(db: Session) -> list[dict[str, Any]]:
    """Resolve every machine that names a bearing. Safe to re-run."""
    ids = db.execute(text("""
        SELECT id FROM equipment_masters
         WHERE bearing_number_de IS NOT NULL OR bearing_number_nde IS NOT NULL
    """)).fetchall()
    out = [resolve_equipment(db, r.id, commit=False) for r in ids]
    db.commit()
    return out
