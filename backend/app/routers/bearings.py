"""Read-only access to the bearing fault frequency catalogue.

The catalogue is reference data — ~89k catalogued parts shared by every tenant,
loaded by `scripts/import_bearing_frequencies.py`. Nothing here writes to it.

It exists so the Equipment Master can turn a bearing the user names into the
four defect frequencies a spectrum is searched for, instead of asking an
engineer to type BPFO and BPFI by hand off a datasheet.
"""
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.bearing import BearingFaultFrequency
from app.schemas.bearing import BearingOut, BearingSearchOut

router = APIRouter(
    prefix="/api/v1/bearings",
    tags=["Bearings"],
    dependencies=[Depends(get_current_user)],
)

#: A search returning thousands of rows helps nobody and costs the browser a
#: lot; the caller narrows by manufacturer if the list is still too broad.
MAX_LIMIT = 50

_PUNCT = re.compile(r"[^A-Z0-9]+")


def normalise_key(text: str) -> str:
    """Match the key the importer wrote: uppercase, punctuation stripped."""
    return _PUNCT.sub("", (text or "").upper())


@router.get("/manufacturers", response_model=list[str])
def list_manufacturers(db: Session = Depends(get_db)) -> list[str]:
    """Every manufacturer code present in the catalogue, alphabetically.

    Declared before `/{source_bearing_id}` on purpose — registered the other
    way round, FastAPI would try to read "manufacturers" as an integer id.
    """
    rows = (
        db.query(BearingFaultFrequency.manufacturer)
        .distinct()
        .order_by(BearingFaultFrequency.manufacturer.asc())
        .all()
    )
    return [row[0] for row in rows]


@router.get("", response_model=BearingSearchOut)
def search_bearings(
    search: Optional[str] = Query(
        default=None,
        description="Part number or manufacturer+part number. Punctuation is ignored.",
    ),
    manufacturer: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=MAX_LIMIT),
    db: Session = Depends(get_db),
) -> BearingSearchOut:
    """Find catalogued bearings by part number.

    Matching is punctuation-insensitive, so "6205-2RS", "6205 2rs" and
    "62052RS" all find the same part. A prefix match on the normalised key
    covers both "SKF6205…" and a bare "6205…".
    """
    query = db.query(BearingFaultFrequency)

    if manufacturer:
        query = query.filter(
            func.upper(BearingFaultFrequency.manufacturer) == manufacturer.upper()
        )

    if search:
        key = normalise_key(search)
        if not key:
            # Punctuation only — nothing to match on, and a bare LIKE '%%' would
            # return the head of an 89k-row table as if it were a result.
            return BearingSearchOut(items=[], count=0, truncated=False)
        pattern = f"{key}%"
        query = query.filter(
            or_(
                BearingFaultFrequency.search_key.like(pattern),
                # The key is manufacturer-prefixed, so a bare part number has to
                # be matched against the designation as well.
                func.replace(
                    func.replace(
                        func.upper(BearingFaultFrequency.designation), "-", ""
                    ),
                    " ",
                    "",
                ).like(pattern),
            )
        )

    # One row over the limit is enough to know the list was cut short, without
    # paying for a full count(*) over a table this size.
    rows = (
        query.order_by(
            BearingFaultFrequency.manufacturer.asc(),
            BearingFaultFrequency.designation.asc(),
            BearingFaultFrequency.source_bearing_id.asc(),
        )
        .limit(limit + 1)
        .all()
    )
    truncated = len(rows) > limit
    items = rows[:limit]

    return BearingSearchOut(
        items=[BearingOut.model_validate(row) for row in items],
        count=len(items),
        truncated=truncated,
    )


@router.get("/{source_bearing_id}", response_model=BearingOut)
def get_bearing(source_bearing_id: int, db: Session = Depends(get_db)) -> BearingOut:
    """One catalogued bearing by its Bearing ID."""
    row = (
        db.query(BearingFaultFrequency)
        .filter(BearingFaultFrequency.source_bearing_id == source_bearing_id)
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No bearing with ID {source_bearing_id} in the catalogue.",
        )
    return BearingOut.model_validate(row)
