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
    # VIK-055. `health_score` may be None where it used to be 100, so the
    # band and the reason travel with it -- a blank cell on a dashboard is
    # read as "fine" unless something says otherwise.
    health_band: Optional[str] = "unknown"
    health_reason: Optional[str] = None
    health_ceiling: Optional[float] = None
    data_quality: Optional[str] = None
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


# ---------------------------------------------------------------------------
# MOM items 10 and 12 — when data arrived, and 7/30-day summaries
# ---------------------------------------------------------------------------

class LastEntryOut(BaseModel):
    """The most recent capture, and how old it is.

    `age_seconds` is computed server-side deliberately: a client comparing its
    own clock against a server timestamp reports the clock skew as data age,
    and "last entry 40 minutes ago" is exactly the figure someone uses to
    decide whether the feed has died.
    """
    capture_id: str
    upload_id: str
    at: datetime
    age_seconds: Optional[float] = None
    machine_name: str
    sensor_location: str
    original_filename: Optional[str] = None
    sample_count: int
    channel_count: int
    sample_rate_hz: float


class EntryDateOut(BaseModel):
    """One calendar day that has data. Empty days are omitted, not zero-filled."""
    date: str
    count: int
    first_at: datetime
    last_at: datetime


class ChannelTrendOut(BaseModel):
    channel_index: int
    rms_mean: float
    rms_min: float
    rms_max: float
    #: Fractional change between the halves of the window, or null when the
    #: data cannot support the claim. Null is the common case early on.
    trend: Optional[float] = None
    direction: str = "unknown"
    trend_blocked_reason: Optional[str] = None


class WindowSummaryOut(BaseModel):
    days: int
    captures: int
    active_days: int
    first_at: Optional[datetime] = None
    last_at: Optional[datetime] = None
    span_hours: float
    #: How much of the window actually contains data. Without this, twenty
    #: captures over forty minutes and over a week read identically.
    coverage_fraction: float
    channels: List[ChannelTrendOut] = []
    note: Optional[str] = None


class CaptureHistoryOut(BaseModel):
    generated_at: datetime
    last_entry: Optional[LastEntryOut] = None
    entries_by_date: List[EntryDateOut] = []
    windows: List[WindowSummaryOut] = []
