"""Response models for the 1x amplitude migration plot."""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ResponseEllipseOut(BaseModel):
    """Geometry of the 1x response ellipse. Casing response — never a shaft orbit."""
    major_axis: float
    minor_axis: float
    orientation_deg: float
    ellipticity: float


class MigrationPointOut(BaseModel):
    """One capture = one point in the Vertical-vs-Horizontal 1x amplitude plane."""
    upload_id: UUID
    captured_at: datetime
    sequence: int
    x_channel: int
    y_channel: int

    #: Magnitudes, so both are >= 0 and the plot sits in the positive quadrant.
    x_amplitude: float
    y_amplitude: float
    x_amplitude_g: float
    y_amplitude_g: float

    #: FFT-derived estimate. Never a measured tachometer reading.
    shaft_frequency_hz: Optional[float] = None
    shaft_rpm: Optional[float] = None
    speed_source: str

    x_phase_deg: Optional[float] = None
    y_phase_deg: Optional[float] = None
    #: phase(Y) - phase(X). Relative only — there is no keyphasor.
    relative_phase_deg: Optional[float] = None

    vector_amplitude: float
    vh_ratio: Optional[float] = None
    bin_hz: Optional[float] = None
    frequency_resolution_hz: Optional[float] = None

    quality: str
    warnings: List[str] = Field(default_factory=list)
    ellipse: Optional[ResponseEllipseOut] = None


class MigrationSummaryOut(BaseModel):
    valid_count: int
    x_max: float
    y_max: float
    shaft_hz_min: Optional[float] = None
    shaft_hz_max: Optional[float] = None


class OneXMigrationOut(BaseModel):
    sensor_id: UUID
    x_channel: int
    y_channel: int
    harmonic: int = 1

    amplitude_unit: str
    source_unit: str
    is_displacement: bool = True

    selection_mode: str
    requested_count: int
    returned_count: int
    total_available: int
    skipped_count: int = 0
    stacking: str = "oldest_to_newest"

    sampling_rate_hz: float

    #: No keyphasor exists, so no absolute shaft phase is available anywhere here.
    keyphasor_available: bool = False
    #: Accelerometers cannot measure static shaft position; this is a response trend.
    is_shaft_centerline: bool = False

    sensor_label: Optional[str] = None
    sensor_orientation: Optional[str] = None
    mounting_location: Optional[str] = None

    points: List[MigrationPointOut]
    summary: MigrationSummaryOut
    warnings: List[str] = Field(default_factory=list)
