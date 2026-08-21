"""Request and response shapes for threshold rule administration.

The column names are the database's, not new ones. The app has three vocabularies
for the same two numbers already — Settings says "Warning / Danger", the health
table says "Caution / Warning", the evaluator says normal_max / warning_max — so
the API declines to invent a fourth and exposes the storage names, with
`limit_labels` on each rule saying how to render them.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.services.threshold_defaults import RULE_TYPES


class ThresholdLimits(BaseModel):
    """The four limit columns. All optional; which ones apply depends on rule_type."""

    normal_max: Optional[float] = None
    warning_max: Optional[float] = None
    normal_min: Optional[float] = None
    warning_min: Optional[float] = None


class ThresholdRuleOut(BaseModel):
    id: UUID
    feature_code: str
    feature_name: Optional[str] = None
    unit: Optional[str] = None
    rule_type: str
    machine_type: Optional[str] = None
    channel: Optional[int] = None
    normal_max: Optional[float] = None
    warning_max: Optional[float] = None
    normal_min: Optional[float] = None
    warning_min: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    updated_at: Optional[datetime] = None
    updated_by: Optional[UUID] = None
    #: True when this row's limits still equal the factory defaults.
    is_default: bool = True
    #: e.g. {"normal_max": "Caution limit", "warning_max": "Warning limit"}
    limit_labels: Dict[str, str] = Field(default_factory=dict)


class ThresholdRuleListOut(BaseModel):
    items: List[ThresholdRuleOut]
    rule_types: Dict[str, Dict[str, Any]]
    #: Channels that carry at least one override, for the coverage matrix.
    overridden_channels: List[int] = Field(default_factory=list)


class ThresholdRuleUpdate(BaseModel):
    normal_max: Optional[float] = None
    warning_max: Optional[float] = None
    normal_min: Optional[float] = None
    warning_min: Optional[float] = None
    is_active: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def _limits_must_ascend(self) -> "ThresholdRuleUpdate":
        _validate_ordering(self.normal_max, self.warning_max, self.normal_min, self.warning_min)
        return self


class ThresholdRuleCreate(BaseModel):
    """Create a channel-specific override of a feature's global rule."""

    feature_code: str
    channel: Optional[int] = Field(default=None, ge=0, le=63)
    machine_type: Optional[str] = None
    rule_type: Optional[str] = None
    normal_max: Optional[float] = None
    warning_max: Optional[float] = None
    normal_min: Optional[float] = None
    warning_min: Optional[float] = None
    is_active: bool = True
    metadata: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def _check(self) -> "ThresholdRuleCreate":
        if self.rule_type is not None and self.rule_type not in RULE_TYPES:
            raise ValueError(f"rule_type must be one of {', '.join(RULE_TYPES)}")
        _validate_ordering(self.normal_max, self.warning_max, self.normal_min, self.warning_min)
        return self


class ThresholdRuleBulkItem(ThresholdRuleUpdate):
    id: UUID


class ThresholdRuleBulkUpdate(BaseModel):
    items: List[ThresholdRuleBulkItem]


def _validate_ordering(
    normal_max: Optional[float],
    warning_max: Optional[float],
    normal_min: Optional[float],
    warning_min: Optional[float],
) -> None:
    """Reject limits the evaluator could never act on.

    evaluate_feature checks normal before warning, so a warning_max at or below
    normal_max makes the warning band empty and the feature jumps straight from
    normal to critical. That is almost always a typo rather than an intent.
    """
    if normal_max is not None and warning_max is not None and warning_max <= normal_max:
        raise ValueError("warning_max must be greater than normal_max")
    if normal_min is not None and warning_min is not None and warning_min >= normal_min:
        raise ValueError("warning_min must be less than normal_min")
    if normal_min is not None and normal_max is not None and normal_min >= normal_max:
        raise ValueError("normal_min must be less than normal_max")
