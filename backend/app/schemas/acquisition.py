from datetime import datetime
from typing import Any, List, Literal, Optional
from uuid import UUID

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel

from app.schemas.measurement import CHANNEL_AXES, CHANNEL_SIGNAL_TYPES, FFT_WINDOWS


class AcquisitionFormulaOut(BaseModel):
    frequencyResolutionHz: float
    blockTimeSeconds: float
    sampleRateHz: float
    requiredSamples: float
    overlapDecimal: float
    totalAcquisitionTimeSeconds: float
    averageCount: float
    fmaxHz: float
    lor: float
    stepSizeSamples: float


class AcquisitionChannelOut(BaseModel):
    transducerType: str
    signalType: str
    channelIndex: int
    machineAxis: str


class EdgeAcquisitionConfigOut(BaseModel):
    acquisitionFormula: AcquisitionFormulaOut
    minutes: str
    averaging: int
    sensitivityMvPerG: Optional[float] = None
    totalChannelCount: int
    averageCount: int
    lastAveraging: Optional[Any] = None
    lastOverlapping: Optional[Any] = None
    lor: str
    fmax: str
    windowType: str
    sensorId: str
    channels: List[AcquisitionChannelOut]
    success: bool = True
    overlapping: int
    ksps: str
    id: int = 1
    overlapPercentage: int
    platformSensorId: str = Field(description="Internal UUID — use for upload API until device_id upload is added")


# ── Public acquisition configuration (Python collector + settings UI) ───────


class AcquisitionCalculatedOut(BaseModel):
    """Derived values. Read-only: the device must not send these back.

    frequencyResolutionHz / blockTimeSeconds / samplesPerBlock follow the
    Nyquist-based LOR convention documented in services/acquisition_config.py:
    samplesPerBlock = 2 * LOR, so Δf = Fs / (2 * LOR).
    """

    frequencyResolutionHz: float
    blockTimeSeconds: float
    samplesPerBlock: int
    totalAcquisitionTimeSeconds: float
    stepSizeSamples: int
    nyquistHz: float
    samplesPerLine: int

    # Fmax-based (portable-analyser) view of the same settings, for comparison
    # only. Never used to compute a spectrum.
    linesBelowFmax: Optional[float] = None
    fmaxRelativeResolutionHz: Optional[float] = None
    fmaxRelativeBlockTimeSeconds: Optional[float] = None


class AcquisitionMappedChannelOut(BaseModel):
    transducerType: str
    signalType: str
    channelIndex: int
    machineAxis: str
    label: Optional[str] = None


class ChannelMapEntryIO(BaseModel):
    """One channel's wiring, in the snake_case shape stored in the database.

    Also accepts the camelCase spelling (`channelIndex`, `machineAxis`,
    `signalType`) so a device can send back the shape it reads from GET.
    """

    # This model is also the GET response shape, and FastAPI serialises response
    # models by alias — so an alias_generator here would rename the output keys
    # and break existing clients. Accept camelCase on input only.
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    channel_index: int = Field(
        ge=1, le=32, validation_alias=AliasChoices("channel_index", "channelIndex")
    )
    machine_axis: str = Field(
        default="VERTICAL",
        validation_alias=AliasChoices("machine_axis", "machineAxis"),
    )
    signal_type: str = Field(
        default="VIBRATION",
        validation_alias=AliasChoices("signal_type", "signalType"),
    )
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


class AcquisitionConfigOut(BaseModel):
    sampleRateHz: float
    ksps: float
    fmaxHz: float
    lor: int
    windowType: str
    averageCount: int
    overlapPercentage: int
    sensitivityMvPerG: Optional[float] = None
    sensitivityUnit: str = "mV/g"
    sensitivitySuspect: bool = Field(
        default=False,
        description="Stored sensitivity is below 1 mV/g, i.e. a placeholder rather than hardware data.",
    )
    totalChannelCount: int
    collectionIntervalMinutes: int

    # Derived values, repeated at the top level so the Python collector can read
    # them without reaching into a nested object. Same numbers as `calculated`.
    frequencyResolutionHz: float
    blockTimeSeconds: float
    samplesPerBlock: int
    totalAcquisitionTimeSeconds: float

    calculated: AcquisitionCalculatedOut
    sensorId: str = Field(description="device_id when set, otherwise the platform UUID")
    platformSensorId: str
    deviceId: Optional[str] = None
    channels: List[AcquisitionMappedChannelOut]
    channelMap: List[ChannelMapEntryIO]
    success: bool = True


class AcquisitionConfigUpdate(BaseModel):
    """Everything the settings page can change. All fields optional — a partial
    save leaves the rest of the stored configuration untouched.

    Accepts both spellings of every field: the snake_case names used in the
    database and the camelCase names GET returns. Unknown keys are rejected
    rather than ignored — a misspelled field used to save with HTTP 200 and
    silently change nothing, which is far worse than a 422.
    """

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid"
    )

    sensor_id: UUID

    sample_rate_hz: Optional[float] = Field(default=None, gt=0, le=10_000_000)
    ksps: Optional[float] = Field(default=None, gt=0, le=10_000)
    fmax_hz: Optional[float] = Field(default=None, gt=0)
    lor: Optional[int] = Field(default=None, ge=64, le=65536)
    window_type: Optional[str] = None
    average_count: Optional[int] = Field(default=None, ge=1, le=256)
    overlap_percentage: Optional[int] = Field(default=None, ge=0, le=100)
    total_channel_count: Optional[int] = Field(default=None, ge=1, le=32)
    collection_interval_minutes: Optional[int] = Field(default=None, ge=1, le=1440)

    sensitivity_mv_per_g: Optional[float] = Field(default=None, gt=0)
    channel_map: Optional[List[ChannelMapEntryIO]] = None

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
    def validate_unique_channels(
        cls, v: Optional[List[ChannelMapEntryIO]]
    ) -> Optional[List[ChannelMapEntryIO]]:
        if v is None:
            return v
        seen: set[int] = set()
        for entry in v:
            if entry.channel_index in seen:
                raise ValueError(f"duplicate channel_index {entry.channel_index}")
            seen.add(entry.channel_index)
        return v

    @model_validator(mode="after")
    def validate_consistency(self):
        # KSPS and Sample Rate are two views of one hardware setting. Accept
        # either, reject a contradiction rather than silently picking a winner.
        if self.ksps is not None and self.sample_rate_hz is not None:
            if abs(self.ksps * 1000.0 - self.sample_rate_hz) > 1e-6:
                raise ValueError(
                    f"ksps ({self.ksps}) and sample_rate_hz ({self.sample_rate_hz}) disagree; "
                    "send one or make them consistent (sample_rate_hz = ksps * 1000)"
                )
        if self.ksps is not None and self.sample_rate_hz is None:
            self.sample_rate_hz = self.ksps * 1000.0

        # Anti-aliasing: content above Nyquist folds back into the spectrum, so
        # an Fmax above it would be reporting frequencies that cannot be
        # measured. Only checkable when both values are known here; the router
        # re-checks against the stored rate for partial saves.
        if self.fmax_hz is not None and self.sample_rate_hz is not None:
            nyquist = self.sample_rate_hz / 2.0
            if self.fmax_hz >= nyquist:
                raise ValueError(
                    f"fmax_hz ({self.fmax_hz} Hz) must stay below Nyquist "
                    f"({nyquist:g} Hz) for sample rate {self.sample_rate_hz:g} Hz"
                )
        return self
