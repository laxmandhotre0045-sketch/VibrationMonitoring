"""Managing a machine's operating modes — VIK-038/039.

The detector refuses to guess what load a machine was under, so a machine
with no bands has every capture labelled unknown and gets no mode-scoped
baseline. `operating_mode_setup` derives one band for a fixed-speed machine
from its equipment record, which covers the common case without anybody
typing anything. This is for the rest: a machine that genuinely runs at
distinct loads, which only somebody who knows it can describe.

**Derived bands can be replaced; they are never silently overwritten.** A
band somebody configured outranks one derived from a record, and the
`source` column says which is which precisely so a later re-derivation
cannot quietly undo a correction.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.operating_mode import UNKNOWN
from app.database import get_db
from app.dependencies.auth import get_current_user, require_write_access
from app.schemas.anomaly import CaptureModeOut, OperatingModeIn, OperatingModeOut
from app.services.operating_mode_setup import ensure_modes_for_equipment

router = APIRouter(
    prefix="/api/v1/operating-modes",
    tags=["Operating modes"],
    dependencies=[Depends(get_current_user)],
)

COLUMNS = ("id, equipment_id, label, rpm_min, rpm_max, load_min, load_max, "
           "source, is_active, notes")


@router.get("", response_model=list[OperatingModeOut])
def list_modes(
    equipment_id: UUID = Query(...),
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Every band defined for this machine.

    An empty list is a real answer and the common one: it means every
    capture on this machine is labelled unknown, which is the engine
    declining to invent what load it was under rather than a failure.
    """
    clause = "" if include_inactive else " AND is_active"
    rows = db.execute(text(f"""
        SELECT {COLUMNS} FROM operating_modes
         WHERE equipment_id = :e {clause}
         ORDER BY rpm_min NULLS FIRST
    """), {"e": str(equipment_id)}).mappings().fetchall()
    return [dict(row) for row in rows]


@router.post("", response_model=OperatingModeOut, status_code=201,
             dependencies=[Depends(require_write_access)])
def create_mode(
    payload: OperatingModeIn,
    equipment_id: UUID = Query(...),
    db: Session = Depends(get_db),
):
    """Define a band somebody who knows the machine can vouch for."""
    if (payload.rpm_min is not None and payload.rpm_max is not None
            and payload.rpm_max < payload.rpm_min):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"The band ends ({payload.rpm_max:g}) before it starts "
            f"({payload.rpm_min:g}), so it would match nothing and send "
            f"every capture to unknown.")
    if payload.rpm_min is None and payload.rpm_max is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "A band with neither end set matches every capture, which would "
            "make every other band on this machine unreachable. Give it at "
            "least one bound.")

    try:
        row = db.execute(text(f"""
            INSERT INTO operating_modes
                (equipment_id, label, rpm_min, rpm_max, load_min, load_max,
                 source, notes)
            VALUES (:e, :label, :rpm_min, :rpm_max, :load_min, :load_max,
                    'configured', :notes)
            RETURNING {COLUMNS}
        """), {"e": str(equipment_id), **payload.model_dump()}).mappings().fetchone()
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This machine already has a mode labelled {payload.label!r}, or "
            f"the label is not one the system recognises. Update the "
            f"existing band rather than adding a second with the same "
            f"name -- two bands with one label is a state every reader "
            f"would resolve differently. ({type(error).__name__})")
    return dict(row)


@router.put("/{mode_id}", response_model=OperatingModeOut,
            dependencies=[Depends(require_write_access)])
def update_mode(
    mode_id: UUID,
    payload: OperatingModeIn,
    db: Session = Depends(get_db),
):
    """Correct a band. A correction is always 'configured', whatever the row
    said before -- somebody has now vouched for it, and a later
    re-derivation must not undo that."""
    row = db.execute(text(f"""
        UPDATE operating_modes
           SET label = :label, rpm_min = :rpm_min, rpm_max = :rpm_max,
               load_min = :load_min, load_max = :load_max,
               notes = :notes, source = 'configured'
         WHERE id = :id
        RETURNING {COLUMNS}
    """), {"id": str(mode_id), **payload.model_dump()}).mappings().fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No mode {mode_id}")
    db.commit()
    return dict(row)


@router.delete("/{mode_id}", status_code=204,
               dependencies=[Depends(require_write_access)])
def deactivate_mode(mode_id: UUID, db: Session = Depends(get_db)):
    """Retire a band without deleting it.

    Deactivated rather than removed, because captures already classified
    into it point at this row. Deleting it would leave those captures
    naming a mode that no longer exists, and a baseline built from them
    unexplainable.
    """
    found = db.execute(text("""
        UPDATE operating_modes SET is_active = false
         WHERE id = :id RETURNING id
    """), {"id": str(mode_id)}).fetchone()
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No mode {mode_id}")
    db.commit()


@router.post("/derive", response_model=list[OperatingModeOut],
             dependencies=[Depends(require_write_access)])
def derive_modes(
    equipment_id: UUID = Query(...),
    db: Session = Depends(get_db),
):
    """Build one band from what the equipment record already says.

    For a fixed-speed machine the operating range is usually already on the
    record, and turning it into a band is reading a field rather than
    guessing. Does nothing if any band already exists: a derived band must
    never overwrite one somebody configured.
    """
    result = ensure_modes_for_equipment(db, equipment_id)
    db.commit()
    if not result["created"] and "no usable speed" in (result.get("reason") or ""):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "This machine's record has no usable speed information, so there "
            "is nothing to derive a band from. Every capture stays unknown "
            "until somebody defines the bands by hand.")
    return list_modes(equipment_id=equipment_id, include_inactive=False, db=db)


@router.get("/capture", response_model=CaptureModeOut)
def capture_mode(
    upload_id: UUID = Query(...),
    db: Session = Depends(get_db),
):
    """Which mode one capture was taken in, and the evidence for it."""
    row = db.execute(text("""
        SELECT upload_id, label, mode_id, is_unknown, confidence, shaft_hz,
               shaft_source, stability, reason
          FROM capture_operating_modes WHERE upload_id = :u
    """), {"u": str(upload_id)}).mappings().fetchone()
    if row is None:
        # Never classified rather than classified as unknown. A caller that
        # treated the two alike would report "we looked and could not tell"
        # about a capture nothing had ever looked at.
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Capture {upload_id} has no operating-mode verdict. It predates "
            f"the detector, or its features have not been computed yet -- "
            f"which is not the same as having been assessed and come back "
            f"{UNKNOWN}.")
    return dict(row)
