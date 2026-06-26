"""Evaluate feature values against threshold rules."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


STATUS_NORMAL = "normal"
STATUS_WARNING = "warning"
STATUS_CRITICAL = "critical"
STATUS_NO_BASELINE = "no_baseline"


@dataclass
class ThresholdRule:
    feature_code: str
    rule_type: str
    normal_max: float | None
    warning_max: float | None
    normal_min: float | None
    warning_min: float | None
    metadata: dict[str, Any]

    @classmethod
    def from_row(cls, row) -> "ThresholdRule":
        meta = row.metadata_ if hasattr(row, "metadata_") else (row.metadata or {})
        return cls(
            feature_code=row.feature_code,
            rule_type=row.rule_type,
            normal_max=float(row.normal_max) if row.normal_max is not None else None,
            warning_max=float(row.warning_max) if row.warning_max is not None else None,
            normal_min=float(row.normal_min) if row.normal_min is not None else None,
            warning_min=float(row.warning_min) if row.warning_min is not None else None,
            metadata=meta or {},
        )


def evaluate_feature(
    feature_code: str,
    value: float,
    rule: ThresholdRule,
    *,
    channel_rms: float | None = None,
    baseline_value: float | None = None,
) -> str:
    rt = rule.rule_type

    if rt == "absolute_max":
        if rule.warning_max is None:
            return STATUS_NORMAL
        normal_cap = rule.normal_max if rule.normal_max is not None else rule.warning_max
        if value <= normal_cap:
            return STATUS_NORMAL
        if value <= rule.warning_max:
            return STATUS_WARNING
        return STATUS_CRITICAL

    if rt == "absolute_db":
        if rule.warning_max is None:
            return STATUS_NORMAL
        normal_cap = rule.normal_max if rule.normal_max is not None else rule.warning_max
        if value <= normal_cap:
            return STATUS_NORMAL
        if value <= rule.warning_max:
            return STATUS_WARNING
        return STATUS_CRITICAL

    if rt == "range":
        n_min = rule.normal_min if rule.normal_min is not None else 0.0
        n_max = rule.normal_max if rule.normal_max is not None else float("inf")
        w_min = rule.warning_min if rule.warning_min is not None else n_min
        w_max = rule.warning_max if rule.warning_max is not None else float("inf")
        if n_min <= value <= n_max:
            return STATUS_NORMAL
        if w_min <= value <= w_max:
            return STATUS_WARNING
        return STATUS_CRITICAL

    if rt == "percent_rms":
        if channel_rms is None or channel_rms < 1e-30:
            return STATUS_NORMAL
        pct = 100.0 * value / channel_rms
        n_max = rule.normal_max or 20.0
        w_max = rule.warning_max or 40.0
        if pct < n_max:
            return STATUS_NORMAL
        if pct < w_max:
            return STATUS_WARNING
        return STATUS_CRITICAL

    if rt == "percent_baseline":
        if baseline_value is None or baseline_value < 1e-30:
            return STATUS_NO_BASELINE
        pct = 100.0 * value / baseline_value
        n_max = rule.normal_max if rule.normal_max is not None else 120.0
        w_max = rule.warning_max if rule.warning_max is not None else 150.0
        crit = float(rule.metadata.get("critical_percent", w_max))
        if pct <= n_max:
            return STATUS_NORMAL
        if pct <= w_max:
            return STATUS_WARNING
        if pct <= crit:
            return STATUS_WARNING
        return STATUS_CRITICAL

    return STATUS_NORMAL


def status_to_health_level(status: str) -> str:
    if status == STATUS_CRITICAL:
        return "Critical"
    if status == STATUS_WARNING:
        return "Warning"
    if status == STATUS_NORMAL:
        return "Normal"
    return "No baseline"
