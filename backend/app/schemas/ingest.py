"""Device-posted measurement payloads.

A device has no interactive login and no file to upload — it holds a block of
samples in memory and posts them as JSON. The shape below deliberately mirrors
what `pdf_parser.parse_sensor_file` produces from a CSV, so an ingested batch
joins the existing parse → plots → features → alerts pipeline unchanged.
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

# A single burst, not a stream. 25.6 kHz for one second across a few channels is
# already ~100k values; anything larger is a device that should be batching into
# separate captures rather than one enormous post.
MAX_SAMPLES_PER_CHANNEL = 262_144
MAX_CHANNELS = 32


class MeasurementIngest(BaseModel):
    device_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Device identifier as registered on the sensor, e.g. 11:AA:BB:CC:DD:EE",
    )
    measured_at: datetime = Field(
        ...,
        description="When the device captured the waveform (ISO 8601). Not the time of posting.",
    )
    channels: Dict[str, List[float]] = Field(
        ...,
        description='Samples per channel, keyed "ch0", "ch1", … — every channel must be the same length.',
    )
    sampling_rate_hz: Optional[float] = Field(
        None,
        gt=0,
        description="Rate this burst was captured at. Falls back to the sensor's stored plot configuration.",
    )
    timestamps: Optional[List[float]] = Field(
        None,
        description="Per-sample seconds. Derived from sampling_rate_hz when omitted.",
    )
    rotation_speed_rpm: Optional[float] = Field(
        None,
        ge=0,
        description="Actual shaft speed during capture. Strongly recommended — fault frequencies scale with it.",
    )

    @field_validator("measured_at")
    @classmethod
    def _no_future_capture(cls, value: datetime) -> datetime:
        """Reject clocks running ahead of the server by more than a slack window.

        Device clocks drift and some never sync at all. A capture stamped in the
        future would sort ahead of everything real and quietly poison trending,
        so it is better rejected at the door than stored.
        """
        reference = datetime.now(timezone.utc)
        candidate = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if (candidate - reference).total_seconds() > 300:
            raise ValueError("measured_at is more than 5 minutes in the future — check the device clock")
        return value

    @field_validator("channels")
    @classmethod
    def _validate_channels(cls, channels: Dict[str, List[float]]) -> Dict[str, List[float]]:
        if not channels:
            raise ValueError("At least one channel is required")
        if len(channels) > MAX_CHANNELS:
            raise ValueError(f"At most {MAX_CHANNELS} channels are supported")

        for name, samples in channels.items():
            if not name.startswith("ch") or not name[2:].isdigit():
                raise ValueError(f"Channel key '{name}' must be of the form ch0, ch1, …")
            if not samples:
                raise ValueError(f"Channel '{name}' contains no samples")
            if len(samples) > MAX_SAMPLES_PER_CHANNEL:
                raise ValueError(
                    f"Channel '{name}' exceeds {MAX_SAMPLES_PER_CHANNEL} samples — split the capture"
                )

        # Channels are indexed positionally downstream, so a gap would silently
        # shift ch2's data into ch1's slot.
        indexes = sorted(int(name[2:]) for name in channels)
        if indexes != list(range(len(indexes))):
            raise ValueError("Channels must be contiguous from ch0 (e.g. ch0, ch1, ch2)")

        lengths = {len(samples) for samples in channels.values()}
        if len(lengths) > 1:
            raise ValueError("Every channel must contain the same number of samples")

        return channels

    @model_validator(mode="after")
    def _validate_timing(self) -> "MeasurementIngest":
        sample_count = len(next(iter(self.channels.values())))

        if self.timestamps is not None and len(self.timestamps) != sample_count:
            raise ValueError(
                f"timestamps has {len(self.timestamps)} entries but each channel has {sample_count} samples"
            )
        if self.timestamps is None and self.sampling_rate_hz is None:
            # Without one or the other there is no time axis, and every spectrum
            # downstream would be plotted against sample index.
            raise ValueError("Provide either timestamps or sampling_rate_hz")

        return self

    @property
    def sample_count(self) -> int:
        return len(next(iter(self.channels.values())))


class MeasurementIngestAck(BaseModel):
    """What the device gets back — enough to log and correlate, nothing more."""

    upload_id: UUID
    sensor_id: UUID
    device_id: str
    sample_count: int
    channel_count: int
    measured_at: datetime
    sampling_rate_hz: float
    parse_status: str
    plots_status: str
    features_status: str
    alerts_raised: int = 0
