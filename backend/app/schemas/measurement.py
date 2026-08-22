from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator, model_validator

PLOT_TYPES = [
    "time_waveform",
    "circular_time_waveform",
    "fft_spectrum",
    "envelope_spectrum",
    "trend_plot",
]

# Legacy aliases from earlier versions
PLOT_TYPE_ALIASES = {
    "psd": "circular_time_waveform",
    "rms_trend": "trend_plot",
}

DATA_TYPES = ["acceleration", "velocity", "displacement"]


class PlotConfigBase(BaseModel):
    channel_count: int = Field(ge=1, le=32)
    active_channel: int = Field(default=0, ge=0)
    sampling_rate_hz: float = Field(default=25600, gt=0)
    fft_lines: int = Field(default=1600, ge=64, le=65536)
    frequency_max_hz: Optional[float] = Field(default=None, gt=0)
    data_type: str = "acceleration"
    enabled_plots: List[str] = Field(default_factory=lambda: list(PLOT_TYPES))

    @field_validator("data_type")
    @classmethod
    def validate_data_type(cls, v: str) -> str:
        if v not in DATA_TYPES:
            raise ValueError(f"data_type must be one of {DATA_TYPES}")
        return v

    @field_validator("enabled_plots")
    @classmethod
    def validate_plots(cls, v: List[str]) -> List[str]:
        normalized: list[str] = []
        for p in v:
            canonical = PLOT_TYPE_ALIASES.get(p, p)
            if canonical in PLOT_TYPES and canonical not in normalized:
                normalized.append(canonical)
        if not normalized:
            raise ValueError(f"enabled_plots must contain valid plot types. Allowed: {PLOT_TYPES}")
        return normalized

class PlotConfigCreate(PlotConfigBase):
    sensor_id: UUID

    @model_validator(mode="after")
    def validate_channel_index(self):
        if self.active_channel >= self.channel_count:
            raise ValueError("active_channel must be less than channel_count")
        return self


class PlotConfigUpdate(BaseModel):
    channel_count: Optional[int] = Field(default=None, ge=1, le=32)
    active_channel: Optional[int] = Field(default=None, ge=0)
    sampling_rate_hz: Optional[float] = Field(default=None, gt=0)
    fft_lines: Optional[int] = Field(default=None, ge=64, le=65536)
    frequency_max_hz: Optional[float] = Field(default=None, gt=0)
    data_type: Optional[str] = None
    enabled_plots: Optional[List[str]] = None


class PlotConfigOut(PlotConfigBase):
    id: UUID
    sensor_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("enabled_plots", mode="before")
    @classmethod
    def normalize_plots_on_read(cls, v: List[str]) -> List[str]:
        if not v:
            return list(PLOT_TYPES)
        normalized: list[str] = []
        for p in v:
            canonical = PLOT_TYPE_ALIASES.get(p, p)
            if canonical in PLOT_TYPES and canonical not in normalized:
                normalized.append(canonical)
        return normalized or list(PLOT_TYPES)

    @model_validator(mode="after")
    def clamp_channel_on_read(self):
        if self.active_channel >= self.channel_count:
            object.__setattr__(self, "active_channel", max(0, self.channel_count - 1))
        return self


class SensorDataUploadOut(BaseModel):
    id: UUID
    sensor_id: UUID
    original_filename: Optional[str] = None
    source: str = "manual"
    channel_count: int
    sample_count: Optional[int]
    parse_status: str
    parse_error: Optional[str]
    plots_status: str = "pending"
    plots_error: Optional[str] = None
    plots_computed_at: Optional[datetime] = None
    features_status: str = "pending"
    features_error: Optional[str] = None
    features_computed_at: Optional[datetime] = None
    created_at: datetime
    measured_at: Optional[datetime] = None
    rotation_speed_rpm: Optional[float] = None
    parsed_at: Optional[datetime]
    has_stored_data: bool = False

    model_config = {"from_attributes": True}


class PaginatedUploadListOut(BaseModel):
    items: List[SensorDataUploadOut]
    total: int
    page: int
    page_size: int


class PlotSeriesOut(BaseModel):
    plot_type: str
    title: str
    x_label: str
    y_label: str
    x: List[float]
    y: List[float]
    channel: int
    metadata: dict = Field(default_factory=dict)


class AllPlotsOut(BaseModel):
    upload_id: UUID
    sensor_id: UUID
    channel: int
    available_channels: List[int] = Field(default_factory=list)
    plots: List[PlotSeriesOut]
