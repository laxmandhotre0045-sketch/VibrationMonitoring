"""Tests for the AI analysis rules — MOM item 4.

What these protect is not "does it produce findings" but "does it refuse to
claim things it cannot support". That direction is the one that matters: an
analyser that over-claims is worse than no analyser, because a confident wrong
statement gets acted on and a missing one gets investigated.

The contexts below are built by hand rather than read from the database, so a
rule can be shown the exact situation it exists for.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.ai_analysis import (
    _rule_instrumentation,
    _rule_machine_state,
    _rule_thresholds,
    _rule_tones,
    _headline,
    _SEVERITY_ORDER,
    RULES,
)
from app.services.ai_context import AIContext, ChannelContext


def ctx(*, running: bool, channels: list[ChannelContext],
        cannot: list[str] | None = None) -> AIContext:
    return AIContext(
        generated_at=datetime.now(timezone.utc),
        machine={"machine_name": "Cooling Water Pump 1"},
        acquisition={"sample_rate_hz": 50000.0},
        data_state={
            "has_data": True,
            "machine_running": running,
            "loudest_channel_ac_rms_g": 0.25 if running else 0.023,
            "idle_ceiling_g": 0.0244,
            "running_threshold_g": 0.035,
            "last_entry_age_seconds": 30,
        },
        channels=channels,
        history={"windows": []},
        cannot_conclude=cannot or [],
        provenance={},
    )


def run_rules(c: AIContext):
    """Every rule, sorted exactly as analyse() sorts them.

    The tests previously passed _headline an UNSORTED list while production
    sorts first. _headline picks hard[0], so the assertions were being made
    against an ordering production never produces -- the test could pass while
    the real headline named a different finding.
    """
    findings = [f for rule in RULES for f in rule(c)]
    findings.sort(key=lambda f: (_SEVERITY_ORDER.get(f.severity, 9),
                                 f.channel_index if f.channel_index is not None else -1))
    return findings


def chan(index=0, **kw) -> ChannelContext:
    base = dict(label=None, machine_axis="VERTICAL", signal_type="VIBRATION")
    base.update(kw)
    return ChannelContext(index=index, **base)


# ------------------------------------------------------- machine state --

def test_idle_machine_is_stated_and_caveated():
    findings = _rule_machine_state(ctx(running=False, channels=[chan()]))
    assert findings[0].code == "machine_idle"
    assert findings[0].caveat and "stationary" in findings[0].caveat.lower()


def test_running_machine_is_stated_without_a_caveat():
    findings = _rule_machine_state(ctx(running=True, channels=[chan()]))
    assert findings[0].code == "machine_running"
    assert findings[0].caveat is None


# ------------------------------------------------------------ thresholds --

def test_breaches_on_an_idle_machine_collapse_to_one_informational_finding():
    """The case that forced the collapse.

    Applying vibration limits to a stationary machine breached something on
    nearly every channel and produced twenty-six findings. Twenty-six findings
    is fewer than seven, because a reader stops at the third.
    """
    channels = [chan(index=i, threshold_status={"rms": "above critical limit 0.02",
                                                "peak": "above warning limit 0.05"})
                for i in range(8)]
    findings = _rule_thresholds(ctx(running=False, channels=channels))
    assert len(findings) == 1
    assert findings[0].severity == "informational"
    assert "machine is stopped" in findings[0].title


def test_breaches_on_a_running_machine_are_reported_individually():
    """The collapse must not swallow real breaches when they matter."""
    channels = [chan(index=i, threshold_status={"rms": "above critical limit 0.02"})
                for i in range(3)]
    findings = _rule_thresholds(ctx(running=True, channels=channels))
    assert len(findings) == 3
    assert all(f.severity == "warning" for f in findings)


def test_values_within_limits_produce_nothing():
    channels = [chan(index=0, threshold_status={"rms": "within limit 0.01"})]
    assert _rule_thresholds(ctx(running=True, channels=channels)) == []


# ----------------------------------------------------------------- tones --

def test_a_tone_on_an_idle_machine_is_not_called_a_machine_order():
    channels = [chan(index=3, dominant_frequency_hz=688.0, dominant_prominence=274.0,
                     dominant_amplitude=0.0297, dominant_is_a_tone=True)]
    findings = _rule_tones(ctx(running=False, channels=channels))
    assert len(findings) == 1
    assert findings[0].caveat and "shaft rotation" in findings[0].caveat
    assert findings[0].confidence == "medium"


def test_channels_sharing_a_frequency_are_reported_as_one_source():
    """ch1, ch3 and ch6 all carry 688 Hz. That is one thing happening."""
    channels = [chan(index=i, dominant_frequency_hz=688.0, dominant_prominence=p,
                     dominant_amplitude=0.01, dominant_is_a_tone=True)
                for i, p in ((1, 36.0), (3, 274.0), (6, 38.0))]
    findings = _rule_tones(ctx(running=False, channels=channels))
    assert len(findings) == 1
    assert "one source, not several" in findings[0].detail


def test_a_channel_below_the_prominence_floor_produces_no_tone_finding():
    channels = [chan(index=0, dominant_frequency_hz=5375.0, dominant_prominence=4.0,
                     dominant_is_a_tone=False)]
    assert _rule_tones(ctx(running=False, channels=channels)) == []


def test_a_mains_channel_is_not_also_reported_as_a_tone():
    """Otherwise the same 50 Hz line appears twice: once correctly as an
    artefact and once as a finding that reads like a machine order."""
    channels = [chan(index=2, dominant_frequency_hz=50.0, dominant_prominence=37.0,
                     dominant_is_a_tone=True,
                     artefacts=["Mains pickup: 50 Hz line at 37x the noise floor."])]
    assert _rule_tones(ctx(running=False, channels=channels)) == []


# -------------------------------------------------------- instrumentation --

def test_mains_ingress_is_a_warning_with_a_fix_instruction():
    channels = [chan(index=2, artefacts=["Mains pickup: 50 Hz line at 37x the floor."])]
    findings = _rule_instrumentation(ctx(running=False, channels=channels))
    assert len(findings) == 1
    assert findings[0].severity == "warning"
    assert findings[0].confidence == "high"
    assert "grounding" in (findings[0].caveat or "")


def test_a_non_mains_artefact_is_not_reported_as_interference():
    channels = [chan(index=0, artefacts=["No tone: the largest line is 4x the floor."])]
    assert _rule_instrumentation(ctx(running=False, channels=channels)) == []


# -------------------------------------------------------------- headline --

def test_headline_on_an_idle_machine_never_claims_a_machine_fault():
    """The headline is the single most quotable line in the payload, so it is
    the one most likely to be repeated without its caveat."""
    channels = [chan(index=i, threshold_status={"rms": "above critical limit 0.02"})
                for i in range(8)]
    c = ctx(running=False, channels=channels)
    head = _headline(c, run_rules(c))
    assert "stopped" in head.lower()
    for word in ("fault", "failure", "defect", "damage"):
        assert word not in head.lower()


def test_headline_names_instrumentation_when_that_is_the_real_problem():
    channels = [chan(index=2, artefacts=["Mains pickup: 50 Hz at 37x."]),
                chan(index=7, artefacts=["Mains pickup: 50 Hz at 34x."])]
    c = ctx(running=False, channels=channels)
    head = _headline(c, run_rules(c))
    assert "mains interference" in head
    assert "2 channel" in head


def test_headline_on_a_clean_running_machine_says_so_plainly():
    c = ctx(running=True, channels=[chan(index=0, threshold_status={"rms": "within limit 0.01"})])
    head = _headline(c, run_rules(c))
    assert "running" in head.lower()
    assert "no measured value is outside its limit" in head


def test_headline_on_a_running_machine_names_the_most_severe_finding():
    """The untested branch. _headline reads findings[0] after sorting, so this
    pins that the sort actually puts the worst item first -- otherwise the
    headline names whichever rule happened to run first."""
    channels = [
        chan(index=0, threshold_status={"rms": "within limit 0.01"}),
        chan(index=5, threshold_status={"rms": "above critical limit 0.02"}),
        chan(index=2, artefacts=["Mains pickup: 50 Hz at 37x."]),
    ]
    c = ctx(running=True, channels=channels)
    findings = run_rules(c)
    head = _headline(c, findings)
    assert "need attention on a running machine" in head
    # whatever it names must be a warning-level finding that actually exists
    named = head.split("the most severe is: ")[-1].rstrip(".")
    assert any(f.title == named and f.severity in ("critical", "warning")
               for f in findings), f"headline named {named!r}, which is not a warning finding"


def test_findings_are_ordered_worst_first():
    """What the severity sort actually controls.

    An earlier attempt tried to pin the ordering through the headline, but
    _headline re-filters to warnings itself, so reversing the sort left it
    unchanged and the test passed against a mutant. The ordering that matters
    is the list a reader scans: informational items must not sit above
    warnings, because a reader stops partway down.
    """
    channels = [
        chan(index=0, threshold_status={"rms": "above critical limit 0.02"}),
        chan(index=2, artefacts=["Mains pickup: 50 Hz at 37x."]),
    ]
    c = ctx(running=True, channels=channels)
    findings = run_rules(c)
    ranks = [_SEVERITY_ORDER[f.severity] for f in findings]
    assert ranks == sorted(ranks), (
        "findings are not worst-first: "
        + ", ".join(f"{f.severity}" for f in findings))
    assert findings[0].severity in ("critical", "warning")


# ------------------------------------------------ mains vs shaft ambiguity --
#
# The pump is rated 1480 rpm, so its shaft turns at 24.67 Hz and its EVEN
# orders land on the mains harmonics: 2x = 49.33 Hz against 50 Hz, 4x = 98.67
# against 100, and so on. At the configured 4 Hz line spacing those share a
# bin. Applied blindly to a running machine, the mains test flagged seven of
# eight channels as electrical.

from app.services.ai_context import (          # noqa: E402
    ARTEFACT_MAINS,
    ARTEFACT_MAINS_AMBIGUOUS,
    _shaft_hz_from_rating,
    _shaft_order_collision,
)


def test_a_shaft_order_landing_on_mains_is_detected_as_a_collision():
    shaft = _shaft_hz_from_rating({"rated_rpm": 1480})
    collides, order, needed = _shaft_order_collision(shaft, resolution_hz=4.0)
    assert collides
    assert order == 2
    assert needed < 0.7, "the resolution asked for must actually separate them"


def test_a_machine_whose_orders_miss_mains_is_not_ambiguous():
    """1750 rpm puts 2x at 58.3 Hz — eight lines clear of mains."""
    shaft = _shaft_hz_from_rating({"rated_rpm": 1750})
    collides, _, _ = _shaft_order_collision(shaft, resolution_hz=4.0)
    assert not collides


def test_finer_resolution_removes_the_ambiguity():
    shaft = _shaft_hz_from_rating({"rated_rpm": 1480})
    assert _shaft_order_collision(shaft, resolution_hz=4.0)[0] is True
    assert _shaft_order_collision(shaft, resolution_hz=0.5)[0] is False


def test_a_missing_or_unusable_rpm_never_raises():
    for bad in ({}, {"rated_rpm": None}, {"rated_rpm": 0}, {"rated_rpm": "n/a"}):
        assert _shaft_hz_from_rating(bad) is None
        assert _shaft_order_collision(_shaft_hz_from_rating(bad), 4.0)[0] is False


def test_an_ambiguous_line_is_reported_not_dropped():
    """The bug this pins.

    Consumers matched the prose prefix "Mains pickup", so the ambiguous
    artefact — introduced later with different wording — was silently dropped
    by every one of them. A reader would have seen a clean channel.
    """
    channels = [chan(index=3, artefacts=[
        f"{ARTEFACT_MAINS_AMBIGUOUS}: 50 Hz line at 139x the noise floor. "
        f"It cannot be separated from the 2x shaft order at 49.33 Hz."])]
    findings = _rule_instrumentation(ctx(running=True, channels=channels))
    assert len(findings) == 1
    assert findings[0].code == "mains_or_shaft_ambiguous"
    assert findings[0].confidence == "low"


def test_an_ambiguous_line_is_not_called_electrical_interference():
    channels = [chan(index=3, artefacts=[f"{ARTEFACT_MAINS_AMBIGUOUS}: 50 Hz line."])]
    findings = _rule_instrumentation(ctx(running=True, channels=channels))
    assert findings[0].code != "mains_ingress"
    assert "electrical interference" not in findings[0].title


def test_an_unambiguous_mains_line_is_still_called_interference():
    """The narrowing must not swallow the real case."""
    channels = [chan(index=2, artefacts=[f"{ARTEFACT_MAINS}: 50 Hz line at 56x."])]
    findings = _rule_instrumentation(ctx(running=False, channels=channels))
    assert findings[0].code == "mains_ingress"
    assert findings[0].severity == "warning"


# ------------------------------------------- the decision itself, not the helpers --
#
# These cover mains_artefact() directly. The decision used to be inline in
# build(), which needs a database, so it was untested -- and a mutation that
# disabled the collision check passed the entire suite.

from app.services.ai_context import mains_artefact          # noqa: E402

CLEAN = {"h1": 2.0, "h2": 1.0, "h3": 1.0, "h4": 1.0}
MAINS_LIKE = {"h1": 56.0, "h2": 8.0, "h3": 9.0, "h4": 34.0}
SHAFT_1480_HZ = 1480 / 60.0


def test_no_artefact_when_there_is_no_50hz_line():
    assert mains_artefact(CLEAN, SHAFT_1480_HZ, 4.0, running=True) is None


def test_no_artefact_when_the_fundamental_has_no_harmonic():
    lonely = {"h1": 56.0, "h2": 2.0, "h3": 1.0, "h4": 1.0}
    assert mains_artefact(lonely, SHAFT_1480_HZ, 4.0, running=False) is None


def test_stopped_machine_gets_an_outright_mains_claim():
    art = mains_artefact(MAINS_LIKE, SHAFT_1480_HZ, 4.0, running=False)
    assert art.startswith(ARTEFACT_MAINS)
    assert "machine is stopped" in art


def test_running_machine_with_a_colliding_order_gets_an_ambiguity():
    """The bug. At 1480 rpm the 2x order is 0.67 Hz from mains and the line
    spacing is 4 Hz, so claiming 'electrical interference' is unsupportable."""
    art = mains_artefact(MAINS_LIKE, SHAFT_1480_HZ, 4.0, running=True)
    assert art.startswith(ARTEFACT_MAINS_AMBIGUOUS)
    assert "2x shaft order" in art
    assert "share a bin" in art


def test_running_machine_whose_orders_miss_mains_still_gets_a_mains_claim():
    """The narrowing must not make the detector useless on other machines."""
    art = mains_artefact(MAINS_LIKE, 1750 / 60.0, 4.0, running=True)
    assert art.startswith(ARTEFACT_MAINS)
    assert ARTEFACT_MAINS_AMBIGUOUS not in art


def test_finer_resolution_restores_the_claim_on_a_running_machine():
    art = mains_artefact(MAINS_LIKE, SHAFT_1480_HZ, 0.5, running=True)
    assert art.startswith(ARTEFACT_MAINS)


def test_unknown_rpm_does_not_block_a_mains_claim():
    """No nameplate means no known collision. Withholding here would hide a
    real instrument fault on every machine with an incomplete record."""
    art = mains_artefact(MAINS_LIKE, None, 4.0, running=True)
    assert art.startswith(ARTEFACT_MAINS)
