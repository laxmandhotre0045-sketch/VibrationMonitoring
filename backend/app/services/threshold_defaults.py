"""Factory threshold limits, and the vocabulary that describes them.

These mirror the rows migration 010 seeds. They live here as well so that
"reset to default" is a real operation rather than a hint, and so a feature that
somehow has no rule can be given one without another migration.

Keep this in step with 010's THRESHOLD_RULES. If the two ever disagree, this
module wins for resets and 010 wins for a fresh database, which is exactly the
kind of drift worth avoiding.
"""
from __future__ import annotations

from typing import Any, NamedTuple


class RuleDefault(NamedTuple):
    rule_type: str
    normal_max: float | None
    warning_max: float | None
    normal_min: float | None
    warning_min: float | None
    metadata: dict[str, Any]


# feature_code -> factory limits
THRESHOLD_RULE_DEFAULTS: dict[str, RuleDefault] = {
    "rms": RuleDefault("absolute_max", 0.01, 0.02, None, None, {}),
    "peak": RuleDefault("absolute_max", 0.05, 0.10, None, None, {}),
    "crest_factor": RuleDefault("range", 3.0, 5.0, 1.4, 3.0, {}),
    "kurtosis": RuleDefault("absolute_max", 3.5, 5.0, None, None, {}),
    "fft_band_energy_0_500": RuleDefault("percent_baseline", 120.0, 150.0, None, None, {}),
    "amplitude_1x": RuleDefault("percent_rms", 20.0, 40.0, None, None, {}),
    "amplitude_2x": RuleDefault("percent_rms", 10.0, 20.0, None, None, {}),
    "amplitude_3x": RuleDefault("percent_rms", 5.0, 15.0, None, None, {}),
    "envelope_rms": RuleDefault(
        "percent_baseline", 100.0, 125.0, None, None, {"critical_percent": 150.0}
    ),
    "noise_floor": RuleDefault("absolute_db", -60.0, -54.0, None, None, {}),
}


RULE_TYPES = (
    "absolute_max",
    "absolute_db",
    "range",
    "percent_rms",
    "percent_baseline",
)


# What the four limit columns mean, per rule type. The API returns this so the
# UI can label and validate a rule without hard-coding the evaluator's branches.
RULE_TYPE_INFO: dict[str, dict[str, Any]] = {
    "absolute_max": {
        "label": "Absolute maximum",
        "unit_kind": "engineering",
        "description": "Value is compared directly against the limits in the feature's own unit.",
        "uses": ["normal_max", "warning_max"],
    },
    "absolute_db": {
        "label": "Absolute (dB)",
        "unit_kind": "db",
        "description": "Same as absolute maximum, but the limits are decibel values and so are usually negative.",
        "uses": ["normal_max", "warning_max"],
    },
    "range": {
        "label": "Acceptable band",
        "unit_kind": "engineering",
        "description": "Normal inside normal_min..normal_max, warning inside warning_min..warning_max, critical outside both.",
        "uses": ["normal_min", "normal_max", "warning_min", "warning_max"],
    },
    "percent_rms": {
        "label": "Percent of channel RMS",
        "unit_kind": "percent",
        "description": "Value is expressed as a percentage of the channel's overall RMS before comparison.",
        "uses": ["normal_max", "warning_max"],
    },
    "percent_baseline": {
        "label": "Percent of baseline",
        "unit_kind": "percent",
        "description": "Value is expressed as a percentage of the saved baseline. Without a baseline the feature reports no_baseline.",
        "uses": ["normal_max", "warning_max"],
    },
}


def default_for(feature_code: str) -> RuleDefault | None:
    return THRESHOLD_RULE_DEFAULTS.get(feature_code)
