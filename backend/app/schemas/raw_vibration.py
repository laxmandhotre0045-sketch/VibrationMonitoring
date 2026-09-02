"""Raw 25 kSPS snapshot upload/read models."""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class RawTimebaseOut(BaseModel):
    """What the time axis actually looked like, as received."""
    sample_count: int
    start_time: float
    end_time: float
    duration_s: float
    mean_step_s: float
    max_step_deviation_s: float
    observed_rate_hz: float
    expected_rate_hz: float
    rate_matches: bool
    uniform: bool


class RawUploadAck(BaseModel):
    """Returned to global_uploader.py after a snapshot is stored."""
    upload_id: UUID
    sensor_id: UUID
    device_id: str
    original_filename: Optional[str] = None
    sample_count: int
    channel_count: int
    sample_rate_hz: float
    measured_at: datetime
    source: str = "device_raw"
    #: Raw path stores verbatim only — no FFT/RMS/peak/kurtosis is computed here.
    derived_artifacts_computed: bool = False
    timebase: RawTimebaseOut
    warnings: List[str] = Field(default_factory=list)


class RawSamplesOut(BaseModel):
    """Windowed raw samples, shaped for direct plotting."""
    upload_id: UUID
    sensor_id: UUID
    device_id: Optional[str] = None
    original_filename: Optional[str] = None
    measured_at: Optional[datetime] = None
    captured_at: datetime

    sample_rate_hz: float = Field(..., alias="sampleRate")
    channel_count: int = Field(..., alias="channelCount")

    #: Window bookkeeping — the browser must never be handed an unbounded series.
    offset: int
    limit: int
    returned: int
    total_samples: int
    has_more: bool
    channels: List[int]

    is_raw: bool = True
    samples: List[Dict[str, Any]]

    model_config = {"populate_by_name": True}


class RawSnapshotSummaryOut(BaseModel):
    """One stored snapshot, without its samples."""
    upload_id: UUID
    sensor_id: UUID
    original_filename: Optional[str] = None
    captured_at: datetime
    measured_at: Optional[datetime] = None
    sample_count: Optional[int] = None
    channel_count: int
    source: Optional[str] = None
    has_raw_samples: bool


class RawSnapshotListOut(BaseModel):
    sensor_id: UUID
    total: int
    items: List[RawSnapshotSummaryOut]


class RawStatisticsOut(BaseModel):
    """Time-domain statistics of one channel of one snapshot."""
    rms: float
    peak: float
    peak_to_peak: float
    crest_factor: float
    #: Excess kurtosis — a Gaussian signal reads 0, not 3.
    kurtosis: float
    skewness: float


class RawSpectrumOut(BaseModel):
    """FFT of one channel, computed by the shared signal_processing code."""
    frequencies: List[float]
    amplitudes: List[float]
    dominant_frequency_hz: float
    dominant_amplitude: float
    line_count: int = Field(description="Spectral lines before thinning for transport")
    returned_points: int
    block_size: int
    averages: int
    frequency_resolution_hz: float


class RawAnalysisOut(BaseModel):
    """Latest-acquisition header, spectrum and statistics for one channel."""
    upload_id: UUID
    sensor_id: UUID
    device_id: Optional[str] = None
    original_filename: Optional[str] = None
    captured_at: datetime
    measured_at: Optional[datetime] = None

    channel: int = Field(description="0-based channel index that was analysed")
    channel_label: Optional[str] = None
    machine_axis: Optional[str] = None
    signal_type: Optional[str] = None

    sample_rate_hz: float
    sample_count: int
    channel_count: int

    spectrum: RawSpectrumOut
    statistics: RawStatisticsOut
