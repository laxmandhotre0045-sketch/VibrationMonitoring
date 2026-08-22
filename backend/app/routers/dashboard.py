from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app import crud
from app.dependencies.auth import get_current_user
from app.schemas.dashboard import DashboardSummaryOut

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
