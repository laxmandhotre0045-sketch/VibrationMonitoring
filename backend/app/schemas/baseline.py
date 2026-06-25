from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class MeasurementUploadDataOut(BaseModel):
    id: UUID
    upload_id: UUID
    sensor_id: UUID
    original_filename: str
    file_format: str
    channel_count: int
    sample_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class BaselineCreateFromUpload(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    labels: List[str] = Field(default_factory=list)
    set_as_primary: bool = False
    captured_at: Optional[datetime] = None


class BaselineOut(BaseModel):
    id: UUID
    sensor_id: UUID
    source_upload_id: Optional[UUID]
    name: str
    description: Optional[str]
    labels: List[str]
    original_filename: str
    file_format: str
    channel_count: int
    sample_count: int
    sampling_rate_hz: float
    is_primary: bool
    captured_at: Optional[datetime]
    created_at: datetime
    plot_count: int = 0
    plots_status: str = "unknown"

    model_config = {"from_attributes": True}


class BaselineSetPrimary(BaseModel):
    is_primary: bool = True


class BaselineListOut(BaseModel):
    sensor_id: UUID
    total: int
    primary_baseline_id: Optional[UUID]
    items: List[BaselineOut]
