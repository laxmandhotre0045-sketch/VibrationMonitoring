"""The shapes the learned-baseline API speaks in — VIK-026, VIK-027.

Written out rather than returned as loose dictionaries because VIK-033
reads these on the other side of the wire, and a frontend that has to
discover the keys by inspecting a response will discover them wrong.

The one rule worth stating: every field that can be unknown is Optional and
is returned as null, never as zero or an empty string. A confidence of 0.0
and a confidence nobody could compute are opposite situations, and a schema
that flattens them into one number is how "no baseline" comes to read as
"perfectly normal".
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class VersionOut(BaseModel):
    version: int
    state: str
    reason: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    activated_at: Optional[datetime] = None
    frozen_at: Optional[datetime] = None
    superseded_at: Optional[datetime] = None
    superseded_by: Optional[int] = None
    age_days: Optional[float] = None


class CoverageOut(BaseModel):
    rows: int
    channels: List[int]
    distinct_features: int
    expected_rows: Optional[int] = None
    #: Null when the caller did not say how many features to expect. A
    #: coverage of 1.0 invented from the rows that happen to exist would
    #: report full coverage for a baseline holding three features.
    fraction: Optional[float] = None


class ConfidenceOut(BaseModel):
    min: Optional[float] = None
    median: Optional[float] = None
    max: Optional[float] = None
    low_confidence_rows: int = 0
    threshold: float


class SamplesOut(BaseModel):
    min: Optional[float] = None
    median: Optional[float] = None
    max: Optional[float] = None
    minimum_required: int
    preferred: int
    below_preferred_rows: int = 0


class FreshnessOut(BaseModel):
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    age_days: Optional[float] = None
    captures_since_window: int = 0
    stale: bool = False
    outgrown: bool = False
    stale_after_days: float


class ExclusionsOut(BaseModel):
    quality_excluded_observations: int = 0
    other_shape_observations: int = 0
    mixed_population_rows: int = 0


class BaselineHealthOut(BaseModel):
    sensor_id: UUID
    available: bool
    #: Why not, when `available` is false. Always populated in that case.
    reason: Optional[str] = None
    version: Optional[VersionOut] = None
    coverage: CoverageOut
    confidence: ConfidenceOut
    samples: SamplesOut
    freshness: FreshnessOut
    exclusions: ExclusionsOut
    #: Plain sentences, worst first, meant to be shown as written. A caller
    #: that shows only one should show the first.
    warnings: List[str] = Field(default_factory=list)
    history: List[VersionOut] = Field(default_factory=list)


class FeatureHealthOut(BaseModel):
    available: bool
    reason: Optional[str] = None
    version: Optional[int] = None
    state: Optional[str] = None
    #: False when the window held more than one population: the median and
    #: spread are still usable, the percentiles are not.
    percentiles_trustworthy: Optional[bool] = None
    sample_count: Optional[int] = None
    confidence: Optional[float] = None
    median: Optional[float] = None
    robust_sigma: Optional[float] = None
    p05: Optional[float] = None
    p95: Optional[float] = None
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    age_days: Optional[float] = None

    model_config = {"extra": "ignore"}


class BaselineWriteIn(BaseModel):
    """A reason is asked for on every write that changes what normal means.

    Not required by the schema, because a scheduled roll has nothing useful
    to say and an empty string would be worse than a null. Required by the
    review that reads the version history six months later, which is why it
    is the first field.
    """
    sensor_id: UUID
    reason: Optional[str] = Field(default=None, max_length=2000)

    model_config = {"extra": "forbid"}


class BaselineResetIn(BaselineWriteIn):
    #: Restrict the window to the last N days. Null learns from everything.
    days: Optional[int] = Field(default=None, gt=0, le=3650)
    #: Build the version but leave it in `building`, so somebody can look at
    #: what was learned before anything is judged against it.
    activate: bool = True


class BaselineRollIn(BaselineWriteIn):
    days: Optional[int] = Field(default=None, gt=0, le=3650)


class BaselineOperationOut(BaseModel):
    sensor_id: UUID
    version: int
    state: str
    stored: int
    refused: int
    captures_in_window: int = 0
    refused_features: List[str] = Field(default_factory=list)
    previous_version: Optional[int] = None
    #: Present when the operation did something other than what was asked --
    #: most importantly when a version was built but not activated because
    #: it learned nothing.
    reason: Optional[str] = None

    model_config = {"extra": "ignore"}


class VersionListOut(BaseModel):
    sensor_id: UUID
    in_force: Optional[VersionOut] = None
    versions: List[VersionOut] = Field(default_factory=list)


def as_dict(payload: Any) -> dict:
    """Small helper so routers stay about routing."""
    return payload if isinstance(payload, dict) else dict(payload)
