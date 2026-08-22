from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class FleetCountsOut(BaseModel):
    total: int = 0
    critical: int = 0
    warning: int = 0
    normal: int = 0
    no_data: int = 0
    average_health_score: Optional[float] = None


class EquipmentHealthOut(BaseModel):
    equipment_id: UUID
    machine_name: str
    machine_id: Optional[str] = None
    plant_name: str
    area: str
    line: str
    machine_type: str
    status: str  # critical | warning | normal | no_baseline | no_data
    health_score: Optional[float] = None
    last_upload_at: Optional[datetime] = None
    worst_feature_name: Optional[str] = None

    model_config = {"from_attributes": True}


class DashboardAlertOut(BaseModel):
    equipment_id: UUID
    machine_name: str
    sensor_id: UUID
    channel: int
    feature_code: str
    feature_name: Optional[str] = None
    status: str
    value: float
    unit: str
    computed_at: datetime


class DashboardActivityOut(BaseModel):
    upload_id: UUID
    equipment_id: UUID
    machine_name: str
    mounting_location: str
    original_filename: Optional[str] = None
    parse_status: str
    features_status: str
    created_at: datetime


class DashboardSummaryOut(BaseModel):
    counts: FleetCountsOut
    equipment_health: List[EquipmentHealthOut]
    alerts: List[DashboardAlertOut]
    recent_activity: List[DashboardActivityOut]
