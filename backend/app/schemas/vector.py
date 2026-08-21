"""Response models for the polar / vibration vector plot."""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class VectorBlockOut(BaseModel):
    """One FFT analysis block of a single capture."""
    block_index: int
    start_sample: int
    time_s: float
    amplitude: float
    #: Raw atan2 result. Absolute only in the arbitrary sense — see phase_reference.
    phase_deg: float
    #: Phase relative to block 0. This is the meaningful quantity.
    relative_phase_deg: float
    is_reference: bool


class VectorDriftOut(BaseModel):
    """Informational bin-mismatch heuristic — never a fault verdict."""
    phase_slope_deg_per_s: Optional[float] = None
    implied_frequency_offset_hz: Optional[float] = None
    amplitude_cv: Optional[float] = None
    linear_fit_r2: Optional[float] = None
    likely_bin_mismatch: bool = False


class FrequencyCandidateOut(BaseModel):
    """A frequency the user can pick as the order of interest."""
    label: str
    frequency_hz: float
    #: "estimated_shaft" (1x/2x/3x) or "peak" (from the stored spectrum).
    source: str
    amplitude: Optional[float] = None


class VibrationVectorOut(BaseModel):
    upload_id: UUID
    sensor_id: UUID
    channel: int
    captured_at: datetime
    original_filename: Optional[str] = None

    sampling_rate_hz: float
    sample_count: int
    window: str
    block_size: int
    block_step: int
    block_count: int
    overlap: float
    block_duration_s: float

    target_hz_requested: float
    bin_hz: float
    bin_index: int
    frequency_resolution_hz: float
    target_source: str
    target_label: str

    amplitude_unit: str
    data_type: str
    amplitude_min: float
    amplitude_max: float

    #: FFT-derived estimate, never a measured tachometer reading. May be null.
    estimated_shaft_hz: Optional[float] = None

    phase_reference: str
    angle_convention: str
    keyphasor_available: bool = False

    sensor_label: Optional[str] = None
    orientation: Optional[str] = None
    mounting_location: Optional[str] = None

    blocks: List[VectorBlockOut]
    drift: VectorDriftOut
    candidates: List[FrequencyCandidateOut] = Field(default_factory=list)
