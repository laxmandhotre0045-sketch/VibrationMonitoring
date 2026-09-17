"""AI endpoints — MOM items 8 and 4.

Two endpoints, deliberately separate:

  /context   what the AI is allowed to reason from (item 8)
  /analysis  what the rules concluded from it (item 4)

Keeping them apart means the contract can be inspected without running the
analysis, and the analysis can be replaced without moving the contract. It also
gives items 5 and 6 -- the bot and the summaries -- something to read that is
not this module's opinion.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.services import ai_analysis, ai_context

router = APIRouter(
    prefix="/api/v1/ai",
    tags=["AI"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/context", summary="The data an AI may reason from (MOM item 8)")
def get_ai_context(
    sensor_id: Optional[UUID] = Query(
        default=None, description="Sensor to describe; omit for the latest capture."),
    db: Session = Depends(get_db),
):
    """Machine details, acquisition settings, per-channel measurements and
    history, each marked with where it came from.

    Every number that can be meaningless carries the measure that says whether
    it is -- a dominant frequency arrives with its prominence, a trend with the
    reason it was withheld. `cannot_conclude` lists the questions this data
    cannot answer, because most bad automated analysis is a right number used
    for the wrong question.
    """
    return ai_context.to_dict(ai_context.build(db, sensor_id))


@router.get("/analysis", summary="Rule-based findings over the context (MOM item 4)")
def get_ai_analysis(
    sensor_id: Optional[UUID] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Findings derived by rule, each with the evidence it fired on.

    Deterministic on purpose: deciding whether a 50 Hz line is a shaft order or
    mains ingress has one correct answer, and a language model asked to decide
    will produce a fluent wrong one when the context is thin. This decides;
    a model can narrate the result.
    """
    return ai_analysis.to_dict(ai_analysis.analyse(db, sensor_id))
