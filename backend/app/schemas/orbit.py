"""Response models for the casing orbit / Lissajous plot."""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CasingOrbitOut(BaseModel):
    upload_id: UUID
    sensor_id: UUID
    captured_at: datetime
    original_filename: Optional[str] = None

    x_channel: int
    y_channel: int
    #: Engineering unit of x_data/y_data. Displacement derived from acceleration.
    amplitude_unit: str = "um"
    source_unit: str = "g"
    #: True when the plotted values are double-integrated displacement.
    is_displacement: bool = True

    sampling_rate_hz: float
    sample_count: int
    record_duration_s: float

    harmonic: int
    centre_hz: float
    lower_hz: float
    upper_hz: float
    frequency_resolution_hz: float
    requested_half_bandwidth_hz: float
    effective_half_bandwidth_hz: float
    effective_bandwidth_percent: float
    bandwidth_sufficient: bool
    required_duration_s: float
    integration_floor_hz: float

    filter_revolutions: int
    available_revolutions: float
    display_revolutions: float
    filter_duration_s: float
    display_duration_s: float

    #: FFT-derived estimate — never a measured tachometer reading.
    estimated_shaft_hz: Optional[float] = None
    shaft_source: str = "estimated_fft"

    x_data: List[float]
    y_data: List[float]
    elapsed_s: List[float]
    revolution: List[float]
    unfiltered_x: Optional[List[float]] = None
    unfiltered_y: Optional[List[float]] = None
    point_count: int
    peak_displacement_um: float

    #: "time_only" until a real keyphasor exists.
    phase_reference: str
    keyphasor_available: bool = False
    #: Numeric probe mounting angles are not stored anywhere, so no X/Y rotation is
    #: applied and the UI must not claim an exact physical orientation.
    mounting_angle_configured: bool = False

    sensor_label: Optional[str] = None
    sensor_orientation: Optional[str] = None
    mounting_location: Optional[str] = None

    warnings: List[str] = Field(default_factory=list)
