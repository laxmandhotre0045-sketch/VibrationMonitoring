"""A definition and a default for every feature — VIK-021.

The platform measures 36 things per channel and could name 10 of them. The
other 26 reached the frontend as bare codes with no unit and no description.

The harder half of this ticket is not the missing rows, it is deciding what
a "default rule" means for a feature nobody has a published limit for. The
requirement already records what happens when someone invents one: a global
RMS limit of 0.02 against a lowest-ever reading of 0.024, and 72 of 72
readings coming back critical. That limit described its own configuration.
"""

from __future__ import annotations

import pytest

from app.services.feature_catalog import (
    FEATURE_DEFINITIONS,
    INFORMATIONAL,
    all_default_rules,
    default_rule_for,
    definition_for,
    seed_rows,
)
from app.services.feature_extraction import FEATURE_CODES
from app.services.threshold_defaults import THRESHOLD_RULE_DEFAULTS
from app.services.threshold_evaluator import (
    STATUS_NORMAL,
    STATUS_NOT_ASSESSED,
    ThresholdRule,
    evaluate_feature,
    status_to_health_level,
)


# ------------------------------------------------------------ completeness --

def test_every_feature_the_extractor_produces_has_a_definition():
    defined = {d.code for d in FEATURE_DEFINITIONS}
    missing = [c for c in FEATURE_CODES if c not in defined]
    assert not missing, f"no definition for {missing}"


def test_nothing_is_defined_that_is_never_produced():
    """A definition with no feature behind it renders an empty row."""
    produced = set(FEATURE_CODES)
    extra = [d.code for d in FEATURE_DEFINITIONS if d.code not in produced]
    assert not extra, f"defined but never produced: {extra}"


def test_the_definition_order_is_the_feature_order():
    """sort_order is the frontend's display order and FEATURE_CODES is a
    positional contract. Two orders that disagree put the labels on the
    wrong columns."""
    assert [d.code for d in FEATURE_DEFINITIONS] == list(FEATURE_CODES)


def test_every_feature_has_a_default_rule():
    rules = all_default_rules()
    assert set(rules) == set(FEATURE_CODES)


def test_every_definition_is_filled_in():
    for d in FEATURE_DEFINITIONS:
        assert d.name and d.name != d.code, f"{d.code} has no human name"
        assert d.unit, f"{d.code} has no unit"
        assert len(d.description) > 20, f"{d.code} has no real description"
        assert d.description.endswith("."), d.code


def test_seed_rows_are_numbered_from_one_without_gaps():
    orders = [r["sort_order"] for r in seed_rows()]
    assert orders == list(range(1, len(FEATURE_DEFINITIONS) + 1))


# ----------------------------------------------- what a default may claim --

def test_the_ten_published_limits_are_not_replaced():
    """Those come from a standard or from physics. A blanket baseline rule
    would throw them away."""
    for code, original in THRESHOLD_RULE_DEFAULTS.items():
        assert default_rule_for(code) is original, code


def test_features_with_no_published_limit_are_judged_against_the_machine():
    """Not against an invented number. Until a baseline exists these report
    "no baseline", which is the truth, rather than "normal", which is not."""
    rule = default_rule_for("spectral_entropy")
    assert rule.rule_type == "percent_baseline"
    assert "no published limit" in rule.metadata["basis"]


def test_no_new_feature_was_given_an_invented_absolute_limit():
    """The failure mode this guards against is in the requirement: one
    absolute limit, set from nothing, that every reading breaches."""
    absolute = {"absolute_max", "absolute_db", "range", "percent_rms"}
    for code, rule in all_default_rules().items():
        if code in THRESHOLD_RULE_DEFAULTS:
            continue
        assert rule.rule_type not in absolute, (
            f"{code} was given an absolute limit with nothing to justify it"
        )


def test_features_where_bigger_is_not_worse_are_never_alarmed_on():
    """A dominant frequency of 97 Hz is a fact about the machine. Grading it
    would report a severity for a number that has no direction."""
    for code in INFORMATIONAL:
        assert default_rule_for(code).rule_type == "informational", code


def test_the_informational_list_only_holds_features_that_exist():
    assert INFORMATIONAL <= set(FEATURE_CODES)


@pytest.mark.parametrize("code", ["dominant_frequency", "dc_offset", "skewness"])
def test_the_obvious_descriptive_features_are_in_that_list(code):
    assert code in INFORMATIONAL


# --------------------------------------------------- not assessed vs normal --

def test_an_informational_feature_reads_not_assessed_not_normal():
    """The distinction this needed a new status for. "Normal" is a judgement;
    these were never judged, and saying normal is how an ungraded feature
    comes to look healthy on a dashboard."""
    rule = ThresholdRule("dominant_frequency", "informational",
                         None, None, None, None, {})
    assert evaluate_feature("dominant_frequency", 97.2, rule) == STATUS_NOT_ASSESSED
    assert evaluate_feature("dominant_frequency", 1e9, rule) == STATUS_NOT_ASSESSED


def test_an_unrecognised_rule_type_is_not_assessed_either():
    """It used to fall through to normal. A rule type nobody implemented is
    not evidence that a machine is fine."""
    rule = ThresholdRule("rms", "some_future_rule_type",
                         None, None, None, None, {})
    assert evaluate_feature("rms", 999.0, rule) == STATUS_NOT_ASSESSED


def test_a_real_rule_still_judges():
    """The new status must not have swallowed the working path."""
    rule = ThresholdRule("rms", "absolute_max", 0.01, 0.02, None, None, {})
    assert evaluate_feature("rms", 0.005, rule) == STATUS_NORMAL


def test_not_assessed_reads_as_words_a_person_can_understand():
    assert status_to_health_level(STATUS_NOT_ASSESSED) == "Not assessed"
    assert status_to_health_level(STATUS_NORMAL) == "Normal"


def test_definition_lookup():
    assert definition_for("rms").name == "RMS"
    assert definition_for("not_a_feature") is None


# ------------------------------------------- counting, and the channel state --

class Row:
    def __init__(self, status):
        self.status = status
        self.computed_at = None


def test_ungraded_features_are_not_counted_as_healthy():
    """The summary cards are read at a glance. Counting an unrecognised
    status as normal turns twenty-six ungraded features into twenty-six
    healthy ones."""
    from app.services.feature_storage import features_summary_from_rows

    rows = [Row("normal"), Row("not_assessed"), Row("not_assessed"),
            Row("something_new"), Row("critical")]
    summary = features_summary_from_rows(rows)

    assert summary["normal"] == 1
    assert summary["critical"] == 1
    assert summary["not_assessed"] == 3, "the unknown status was counted elsewhere"
    assert summary["total"] == 5
    assert sum(summary[k] for k in
               ("normal", "warning", "critical", "no_baseline", "not_assessed")) == 5


def test_the_channel_state_does_not_depend_on_row_order():
    """It used to fall back to whichever row came first, so the same channel
    could read differently depending on how the query sorted."""
    from app.routers.measurements import _channel_health_overview

    mixture = [Row("not_assessed"), Row("no_baseline"), Row("not_assessed")]
    first = _channel_health_overview(mixture, {}).health_state
    second = _channel_health_overview(list(reversed(mixture)), {}).health_state
    assert first == second == "No baseline"


@pytest.mark.parametrize("statuses,expected", [
    (["critical", "normal", "not_assessed"], "Critical"),
    (["warning", "normal", "not_assessed"], "Warning"),
    (["normal", "not_assessed", "no_baseline"], "Normal"),
    (["no_baseline", "not_assessed"], "No baseline"),
    (["not_assessed", "not_assessed"], "Not assessed"),
])
def test_the_worst_graded_status_decides_the_channel(statuses, expected):
    """Ungraded features must not make a channel look worse, and must not
    make it look better either."""
    from app.routers.measurements import _channel_health_overview

    assert _channel_health_overview([Row(s) for s in statuses], {}).health_state == expected


# ---------------------------------------- level features measure the machine --

def test_rms_peak_and_crest_ignore_a_standing_bias():
    """The largest single source of false alarms the platform had.

    A transducer's resting position is not vibration. Including it made five
    of the pump's eight channels read critical against the 0.02 limit while
    their actual movement was 0.0025 to 0.005 -- and 1,163 of 1,479 critical
    rows in the whole database came from these three features measuring the
    sensor instead of the machine.
    """
    import numpy as np
    from app.services.feature_extraction import extract_channel_features

    fs, n = 25600.0, 8192
    t = np.arange(n) / fs
    vibration = 0.006 * np.sin(2 * np.pi * 120.0 * t)

    clean = extract_channel_features(vibration.tolist(), fs)
    biased = extract_channel_features((vibration - 0.144).tolist(), fs)

    for code in ("rms", "peak", "crest_factor"):
        assert biased[code]["value"] == pytest.approx(clean[code]["value"], rel=1e-6), (
            f"{code} moved when a constant -0.144 g was added"
        )

    # and the value is the vibration, not the bias
    assert biased["rms"]["value"] == pytest.approx(0.006 / np.sqrt(2), rel=0.01)
    assert biased["rms"]["value"] < 0.01, "this channel must not grade as critical"


def test_crest_factor_of_a_biased_sine_is_still_the_crest_of_a_sine():
    """With the bias in both the numerator and the denominator, a badly
    biased channel drifts towards 1.0 -- the value that means a pure sine --
    whatever it is actually doing."""
    import numpy as np
    from app.services.feature_extraction import extract_channel_features

    fs, n = 25600.0, 8192
    sine = 0.01 * np.sin(2 * np.pi * 100.0 * np.arange(n) / fs)
    biased = extract_channel_features((sine - 0.2).tolist(), fs)

    assert biased["crest_factor"]["value"] == pytest.approx(np.sqrt(2), rel=0.02)
