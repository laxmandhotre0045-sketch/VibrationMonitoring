"""Response models for the 3D FFT waterfall (many captures, one channel)."""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

SELECTION_MODES = ["last", "oldest", "random"]
STACKING_OLDEST_TO_NEWEST = "oldest_to_newest"


class WaterfallPeakOut(BaseModel):
    """A detected spectral peak within one capture."""
    frequency: float
    amplitude: float


class WaterfallCaptureOut(BaseModel):
    """One FFT spectrum = one upload = one row of the waterfall."""
    capture_number: int = Field(description="1-based position in stacking order (oldest -> newest)")
    upload_id: UUID
    original_filename: Optional[str] = None
    captured_at: datetime
    channel: int
    point_count: int
    frequencies: List[float]
    amplitudes: List[float]
    peaks: List[WaterfallPeakOut] = Field(default_factory=list)


class WaterfallOut(BaseModel):
    sensor_id: UUID
    channel: int
    plot_type: str
    selection_mode: str
    stacking: str = STACKING_OLDEST_TO_NEWEST

    requested_count: int
    returned_count: int
    total_available: int
    skipped_count: int = 0

    sampling_rate_hz: float
    fft_lines: Optional[int] = None
    window: str
    data_type: str

    frequency_min_hz: Optional[float] = None
    frequency_max_hz: Optional[float] = None
    frequency_resolution_hz: Optional[float] = None
    amplitude_min: Optional[float] = None
    amplitude_max: Optional[float] = None

    x_label: str
    y_label: str
    z_label: str

    sensor_label: Optional[str] = None
    orientation: Optional[str] = None
    mounting_location: Optional[str] = None

    captures: List[WaterfallCaptureOut]
