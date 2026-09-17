from typing import Optional

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app import crud
from app.dependencies.auth import get_current_user
from app.schemas.dashboard import CaptureHistoryOut, DashboardSummaryOut
from app.services import capture_history

router = APIRouter(
    prefix="/api/v1/dashboard",
    tags=["Dashboard"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/summary", response_model=DashboardSummaryOut)
def get_dashboard_summary(
    plant_name: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return crud.get_dashboard_summary(db, plant_name=plant_name)


@router.get("/history", response_model=CaptureHistoryOut,
            summary="When data arrived, and 7/30-day summaries (MOM items 10 and 12)")
def get_capture_history(
    sensor_id: Optional[UUID] = Query(
        default=None,
        description="Restrict to one sensor; omit for every sensor that has data.",
    ),
    db: Session = Depends(get_db),
):
    """Capture history for the dashboard cards.

    Windows report their real coverage alongside their counts, and a trend is
    returned as null with a reason whenever the underlying data could not
    support one -- which, early in a deployment, is most of the time.
    """
    return capture_history.history(db, sensor_id=sensor_id)
