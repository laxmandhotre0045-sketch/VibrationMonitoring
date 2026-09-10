from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.passthrough import RowPassthrough

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

#: Acquisition windows an edge device can be asked to apply.
FFT_WINDOWS = ["HANNING", "HAMMING", "RECTANGULAR", "FLATTOP", "BLACKMAN"]

#: Measurement direction a DAQ channel is wired to. Casing accelerometers are
#: mounted in one of three directions relative to the shaft.
CHANNEL_AXES = ["VERTICAL", "HORIZONTAL", "AXIAL"]

#: What a channel measures. Kept open-ended but validated so the edge device
#: never receives a blank signal type.
CHANNEL_SIGNAL_TYPES = ["VIBRATION", "TEMPERATURE", "PRESSURE", "TACHO"]


class ChannelMapEntry(BaseModel):
    """One DAQ channel's wiring: CH1..CHn mapped to a measurement direction."""

    channel_index: int = Field(ge=1, le=32, description="1-based channel number (CH1 = 1)")
    machine_axis: str = Field(default="VERTICAL")
    signal_type: str = Field(default="VIBRATION")
    label: Optional[str] = Field(default=None, max_length=80)

    @field_validator("machine_axis")
    @classmethod
    def validate_axis(cls, v: str) -> str:
        upper = (v or "").strip().upper()
        if upper not in CHANNEL_AXES:
            raise ValueError(f"machine_axis must be one of {CHANNEL_AXES}")
        return upper

    @field_validator("signal_type")
    @classmethod
    def validate_signal_type(cls, v: str) -> str:
        upper = (v or "").strip().upper()
        if upper not in CHANNEL_SIGNAL_TYPES:
            raise ValueError(f"signal_type must be one of {CHANNEL_SIGNAL_TYPES}")
        return upper


def _validate_channel_map(v: Optional[List[ChannelMapEntry]]) -> Optional[List[ChannelMapEntry]]:
    """Reject duplicate channel numbers — the device indexes by channel_index."""
    if v is None:
        return v
    seen: set[int] = set()
    for entry in v:
        if entry.channel_index in seen:
            raise ValueError(f"duplicate channel_index {entry.channel_index} in channel_map")
        seen.add(entry.channel_index)
    return v


class PlotConfigBase(BaseModel):
    channel_count: int = Field(ge=1, le=32)
    active_channel: int = Field(default=0, ge=0)
    sampling_rate_hz: float = Field(default=25600, gt=0)
    fft_lines: int = Field(default=1600, ge=64, le=65536)
    frequency_max_hz: Optional[float] = Field(default=None, gt=0)
    data_type: str = "acceleration"
    enabled_plots: List[str] = Field(default_factory=lambda: list(PLOT_TYPES))

    # DAQ acquisition settings for the edge device.
    window_type: str = "HANNING"
    averaging: int = Field(default=1, ge=1, le=256)
    overlap_percent: int = Field(default=0, ge=0, le=100)

    # MQTT acquisition (migration 017). collection_interval_minutes is the
    # cadence between captures, unrelated to sampling_rate_hz and block time.
    collection_interval_minutes: int = Field(default=2, ge=1, le=1440)
    channel_map: List[ChannelMapEntry] = Field(default_factory=list)
    mqtt_broker: Optional[str] = Field(default=None, max_length=255)
    mqtt_port: int = Field(default=1883, ge=1, le=65535)
    mqtt_topic: str = Field(default="Vibration_Data", min_length=1, max_length=255)

    @field_validator("window_type")
    @classmethod
    def validate_window(cls, v: str) -> str:
        upper = (v or "").upper()
        if upper not in FFT_WINDOWS:
            raise ValueError(f"window_type must be one of {FFT_WINDOWS}")
        return upper

    @field_validator("channel_map")
    @classmethod
    def validate_channel_map(cls, v: List[ChannelMapEntry]) -> List[ChannelMapEntry]:
        return _validate_channel_map(v) or []

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
    window_type: Optional[str] = None
    averaging: Optional[int] = Field(default=None, ge=1, le=256)
    overlap_percent: Optional[int] = Field(default=None, ge=0, le=100)
    collection_interval_minutes: Optional[int] = Field(default=None, ge=1, le=1440)
    channel_map: Optional[List[ChannelMapEntry]] = None
    mqtt_broker: Optional[str] = Field(default=None, max_length=255)
    mqtt_port: Optional[int] = Field(default=None, ge=1, le=65535)
    mqtt_topic: Optional[str] = Field(default=None, min_length=1, max_length=255)

    @field_validator("window_type")
    @classmethod
    def validate_window(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        upper = v.upper()
        if upper not in FFT_WINDOWS:
            raise ValueError(f"window_type must be one of {FFT_WINDOWS}")
        return upper

    @field_validator("channel_map")
    @classmethod
    def validate_channel_map(
        cls, v: Optional[List[ChannelMapEntry]]
    ) -> Optional[List[ChannelMapEntry]]:
        return _validate_channel_map(v)


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


class SensorDataUploadOut(RowPassthrough):
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

    # from_attributes comes from RowPassthrough, along with the column sweep.


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
