"""The shapes the Phase 2 API speaks in — VIK-041 to VIK-046.

Written out rather than returned as loose dictionaries, for the reason the
learned-baseline schemas were: a frontend that has to discover the keys by
inspecting a response will discover them wrong.

One rule runs through all of it, and it is the same rule the engines
enforce: **anything that can be unknown is Optional and comes back as null,
never as zero.** A score of 0 and a score nobody could compute are opposite
findings. Flattening them is how an unmonitored machine comes to look
healthier than a monitored one, and it is the single mistake this whole
platform is built to refuse.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ----------------------------------------------------- scores ----------

class FeatureScoreOut(BaseModel):
    channel: int
    feature_code: str
    #: Null when nothing could be scored. `is_scored` carries the meaning so
    #: no caller has to interpret a null, and none can mistake it for zero.
    score: Optional[float] = None
    band: Optional[str] = None
    is_scored: bool
    #: Signed. A bearing band that collapses is as interesting as one that
    #: climbs, and a magnitude loses the difference between a machine
    #: getting worse and a sensor falling off.
    z_score: Optional[float] = None
    #: How much the comparison is worth, separate from how unusual the
    #: reading is. Never multiplied into the score.
    confidence: float = 0.0
    baseline_version: Optional[int] = None
    mode_id: Optional[UUID] = None
    reason: Optional[str] = None
    contributions: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "ignore"}


class CaptureScoresOut(BaseModel):
    upload_id: UUID
    sensor_id: UUID
    scored: int
    unscored: int
    mode_id: Optional[UUID] = None
    mode_label: Optional[str] = None
    worst: Optional[FeatureScoreOut] = None
    scores: List[FeatureScoreOut] = Field(default_factory=list)


class ScoredCaptureOut(BaseModel):
    """One capture that has actually been scored, for a capture picker.

    `features_status` on the upload cannot answer this. On this platform 157
    uploads say "pending" while 120 of them carry scores -- the column is
    written by the ingest path and the scores were also written by backfill
    scripts that never touched it. Asking the score table directly is the
    only answer that is true.
    """
    upload_id: UUID
    created_at: datetime
    scored: int
    unscored: int
    worst_score: Optional[float] = None
    worst_band: Optional[str] = None
    mode_label: Optional[str] = None


# --------------------------------------------------- detectors ---------

class DetectorDriverOut(BaseModel):
    feature: str
    #: Share of the residual this feature accounts for, 0-1.
    share: float


class DetectorScoreOut(BaseModel):
    channel: int
    method: str
    score: Optional[float] = None
    is_scored: bool
    #: The detector's own output. The 0-100 mapping is a presentation
    #: choice; this is the evidence behind it.
    raw: Optional[float] = None
    #: Which features drove the residual, worst first. Empty for Isolation
    #: Forest, which does not decompose.
    drivers: List[DetectorDriverOut] = Field(default_factory=list)
    training_samples: Optional[int] = None
    reason: Optional[str] = None

    model_config = {"extra": "ignore"}


# ------------------------------------------------------ alarms ---------

class AlarmOut(BaseModel):
    channel: int
    feature_code: str
    score: Optional[float] = None
    band: Optional[str] = None
    confidence: Optional[float] = None
    #: Consecutive captures past the line, and how many this machine's
    #: sensitivity setting requires. Both, because "3 of 3" and "3 of 4"
    #: are the difference between ringing and not.
    run_length: int = 0
    required: int = 0
    #: When this fault *first* started, kept across a dip below the line.
    #: The one fact here that cannot be recomputed from the scores, and the
    #: one a maintenance engineer most wants.
    first_alarmed_at: Optional[datetime] = None
    last_alarmed_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    reason: Optional[str] = None

    model_config = {"extra": "ignore"}


class HeldBackOut(AlarmOut):
    #: 'not_persistent' or 'low_confidence'. Why this finding is past the
    #: line and still not ringing -- which somebody adjusting the
    #: sensitivity profile needs to see, because the two have different
    #: fixes.
    held_back: str


class AlarmSummaryOut(BaseModel):
    sensor_id: UUID
    profile: str
    alarming: int
    held_back: int
    alarms: List[AlarmOut] = Field(default_factory=list)
    suppressed: List[HeldBackOut] = Field(default_factory=list)


class AcknowledgeIn(BaseModel):
    sensor_id: UUID
    channel: int
    feature_code: str = Field(min_length=1, max_length=64)
    note: Optional[str] = Field(default=None, max_length=2000)

    model_config = {"extra": "forbid"}


# ------------------------------------------------- sensitivity ---------

class SensitivityOut(BaseModel):
    equipment_id: UUID
    profile: str
    #: The four numbers the profile actually sets. Returned even for the
    #: presets, so a settings screen can show what choosing one will do
    #: rather than describing it in prose.
    score_threshold: float
    persistence: int
    min_confidence: float
    baseline_days: Optional[int] = None
    expert_overrides: dict[str, Any] = Field(default_factory=dict)
    updated_by: Optional[str] = None
    updated_at: Optional[datetime] = None


class SensitivityIn(BaseModel):
    profile: str = Field(min_length=1, max_length=20)
    #: Read only when profile is 'expert', and kept when the profile is
    #: switched away and back so tuning is not lost.
    overrides: Optional[dict[str, Any]] = None

    model_config = {"extra": "forbid"}


# --------------------------------------------- operating modes ---------

class OperatingModeOut(BaseModel):
    id: UUID
    equipment_id: UUID
    label: str
    rpm_min: Optional[float] = None
    rpm_max: Optional[float] = None
    load_min: Optional[float] = None
    load_max: Optional[float] = None
    #: 'configured' by a person or 'discovered' from history. A discovered
    #: band must never silently overwrite a configured one.
    source: str
    is_active: bool = True
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class OperatingModeIn(BaseModel):
    label: str = Field(min_length=1, max_length=32)
    rpm_min: Optional[float] = Field(default=None, gt=0)
    rpm_max: Optional[float] = Field(default=None, gt=0)
    load_min: Optional[float] = None
    load_max: Optional[float] = None
    notes: Optional[str] = Field(default=None, max_length=2000)

    model_config = {"extra": "forbid"}


class CaptureModeOut(BaseModel):
    upload_id: UUID
    label: str
    mode_id: Optional[UUID] = None
    #: True when nothing matched. The label is then 'unknown', and the two
    #: always agree -- a database constraint sees to that.
    is_unknown: bool
    confidence: float = 0.0
    shaft_hz: Optional[float] = None
    shaft_source: Optional[str] = None
    stability: Optional[str] = None
    reason: Optional[str] = None

    model_config = {"extra": "ignore"}
