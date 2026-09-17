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
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.services import ai_analysis, ai_bot, ai_context, ai_summary, llm

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


@router.get("/summary", summary="Plain-language summary and suggestions (MOM item 6)")
def get_ai_summary(
    sensor_id: Optional[UUID] = Query(default=None),
    db: Session = Depends(get_db),
):
    """The findings, said in a sentence someone can act on.

    A language model narrates what the rules decided, and the text is verified
    before it is returned: every number in it must appear in the findings it
    was given. If there is no API key, the call fails, or verification rejects
    the text, the platform writes the summary itself and says so in `source`.
    """
    return ai_summary.to_dict(ai_summary.build(db, sensor_id))


@router.get("/status", summary="Whether a language model is configured")
def get_ai_status():
    """Surfaced so a blank narration is diagnosable from the UI rather than
    looking like a bug."""
    return {
        "llm_configured": llm.is_configured(),
        "model": llm.model_name() if llm.is_configured() else None,
    }


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    sensor_id: Optional[UUID] = None


@router.post("/ask", summary="Ask a question about this machine (MOM item 5)")
def ask_ai(payload: AskRequest, db: Session = Depends(get_db)):
    """Answers from the findings, or refuses.

    A refusal is a normal outcome, not an error: the data cannot answer most
    questions about a stopped machine, and `refused_reason` says which. Answers
    are verified the same way summaries are -- every number must appear in the
    findings -- and an answer that fails is withheld rather than shown with a
    warning, because there is no template to fall back to.
    """
    return ai_bot.to_dict(ai_bot.ask(db, payload.question, payload.sensor_id))
