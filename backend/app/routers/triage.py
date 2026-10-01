"""The priority queue and the feedback loop over HTTP — sections 15 and 16.

Five endpoints. The queue is the one a maintenance team opens in the
morning; the rest are how they answer it.

**Feedback is a POST that returns what it changed.** Not an acknowledgement
-- the actual effect, in words. An analyst who marks something a false
alarm and gets back "recorded" has no reason to believe anything happened,
and will stop bothering. Section 16.2 is a promise that the feedback is
used, and the response is where that promise is kept or broken.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai.feedback import SUPPRESSION_DAYS, VERDICTS, describe
from app.database import get_db
from app.dependencies.auth import get_current_user, require_write_access
from app.services import triage_storage

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/triage",
    tags=["Triage"],
    dependencies=[Depends(get_current_user)],
)


class FeedbackIn(BaseModel):
    verdict: str = Field(..., description="One of section 16.1's options")
    note: Optional[str] = Field(
        None, description="Required when muting a fault.")
    corrected_fault_key: Optional[str] = None
    corrected_fault_label: Optional[str] = None
    corrected_severity: Optional[int] = Field(None, ge=0, le=5)
    retracts_id: Optional[UUID] = Field(
        None, description="A previous report this one withdraws.")
    suppression_days: int = Field(SUPPRESSION_DAYS, ge=1, le=365)


class AssignIn(BaseModel):
    analyst: Optional[str] = Field(
        None, description="Null to unassign.")
    status: Optional[str] = None


@router.get("/queue", summary="Which machine to attend to first (15.2)")
def queue(
    limit: int = Query(50, ge=1, le=200),
    include_suppressed: bool = Query(
        False, description="Include findings an analyst has muted."),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """The priority queue, worst first, recomputed on every request.

    Recomputed rather than read from a stored rank: priority depends on the
    machine's criticality, on how well the last capture could be trusted,
    and on what analysts have said since -- all of which move independently
    of the fault. A stored rank goes stale silently, which is worse than
    none because it still looks current.
    """
    rows = triage_storage.queue(db, limit=limit,
                                include_suppressed=include_suppressed)
    return {
        "queue": rows, "count": len(rows),
        "reason": (
            "Nothing is currently open on any machine. On this gateway that "
            "is not a clean bill of health -- no capture can yet resolve the "
            "bearing frequencies, so no fault rule can fire."
            if not rows else
            f"{len(rows)} finding(s) ranked. Priority combines how bad the "
            f"fault is with how much the machine matters, scaled down by how "
            f"well it can be seen."),
    }


@router.get("/verdicts", summary="What an analyst can say, and what it does")
def verdicts() -> dict[str, Any]:
    """Section 16.1's options with section 16.2's consequences.

    The `effect` field is what the platform actually changes today. Where
    a verdict is recorded but does not yet alter behaviour, it says so
    rather than implying it is being learned from.
    """
    return {"verdicts": [{"value": key, **value}
                         for key, value in VERDICTS.items()],
            "count": len(VERDICTS)}


@router.post("/findings/{finding_id}/feedback",
             dependencies=[Depends(require_write_access)],
             summary="Record an analyst's verdict (16.1)")
def feedback(
    finding_id: UUID,
    body: FeedbackIn,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Append one report and apply whatever it changes.

    Appended, never updated: an analyst can change their mind and a second
    can disagree with the first, and a single mutable verdict column
    represents neither. A withdrawal is another row, not a delete.
    """
    analyst = (user.get("email") or user.get("id") or "unknown"
               if isinstance(user, dict) else str(user))
    try:
        result = triage_storage.record_feedback(
            db, finding_id=finding_id, verdict=body.verdict,
            analyst=analyst, note=body.note,
            corrected_fault_key=body.corrected_fault_key,
            corrected_fault_label=body.corrected_fault_label,
            corrected_severity=body.corrected_severity,
            retracts_id=body.retracts_id,
            suppression_days=body.suppression_days)
        db.commit()
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception:
        db.rollback()
        logger.exception("Could not record feedback on %s", finding_id)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="The feedback could not be recorded.")
    return result


@router.post("/findings/{finding_id}/assign",
             dependencies=[Depends(require_write_access)],
             summary="Assign an analyst and set status (15.2)")
def assign(
    finding_id: UUID,
    body: AssignIn,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = triage_storage.assign(db, finding_id=finding_id,
                                       analyst=body.analyst,
                                       status=body.status)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not assign %s", finding_id)
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail="The finding could not be assigned.")
    if not result:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail=f"No finding {finding_id}")
    return result


@router.get("/feedback/summary",
            summary="What the loop has collected, and what it is doing (16.2)")
def summary(db: Session = Depends(get_db)) -> dict[str, Any]:
    """How anyone checks the feedback is feeding something back.

    Section 16.2 lists five uses for the feedback. A table that accumulates
    verdicts nothing reads satisfies none of them, and the only way to tell
    the difference from outside is to ask what it has changed.
    """
    return triage_storage.feedback_summary(db)
