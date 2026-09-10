from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.passthrough import RowPassthrough


class ChannelFeatureOut(RowPassthrough):
    channel: int
    feature_code: str
    feature_name: Optional[str] = None
    value: float
    unit: str
    status: str
    metadata: dict = Field(default_factory=dict)
    computed_at: datetime

    # from_attributes comes from RowPassthrough, along with the column sweep.


class FeaturesSummaryOut(BaseModel):
    normal: int = 0
    warning: int = 0
    critical: int = 0
    no_baseline: int = 0
    total: int = 0


class ChannelHealthOverviewOut(BaseModel):
    health_state: str
    feature_count: int
    computed_at: Optional[datetime] = None
    baseline_name: Optional[str] = None
    baseline_id: Optional[UUID] = None


class UploadFeaturesOut(BaseModel):
    upload_id: UUID
    sensor_id: UUID
    channel: Optional[int] = None
    features_status: str
    features_error: Optional[str] = None
    features_computed_at: Optional[datetime] = None
    items: List[ChannelFeatureOut]
    summary: FeaturesSummaryOut
    channel_overview: ChannelHealthOverviewOut


class FactorTrendSeriesOut(BaseModel):
    feature_code: str
    feature_name: str
    unit: str
    value: float
    status: str
    trend_x: List[float]
    trend_y: List[float]


class UploadFactorTrendsOut(BaseModel):
    upload_id: UUID
    sensor_id: UUID
    channel: int
    features_status: str
    sampling_rate_hz: float
    #: When the capture was taken. trend_x is an offset in seconds from this
    #: instant, so without it the chart can only label the x axis in bare
    #: seconds. measured_at (the device clock) is preferred over created_at
    #: (server receipt) because only the former orders a trend correctly.
    captured_at: Optional[datetime] = None
    factors: List[FactorTrendSeriesOut]


class BaselineFeaturesOut(BaseModel):
    baseline_id: UUID
    sensor_id: UUID
    channel: Optional[int] = None
    items: List[ChannelFeatureOut]
    summary: FeaturesSummaryOut


class FeatureCompareItemOut(BaseModel):
    channel: int
    feature_code: str
    feature_name: Optional[str] = None
    unit: str
    upload_value: float
    baseline_value: Optional[float] = None
    percent_of_baseline: Optional[float] = None
    status: str


class FeatureCompareOut(BaseModel):
    upload_id: UUID
    baseline_id: UUID
    channel: Optional[int] = None
    items: List[FeatureCompareItemOut]
    summary: FeaturesSummaryOut
