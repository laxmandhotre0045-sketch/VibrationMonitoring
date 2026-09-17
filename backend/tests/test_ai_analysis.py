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
    findings = [f for rule in RULES for f in rule(c)]
    head = _headline(c, findings)
    assert "stopped" in head.lower()
    for word in ("fault", "failure", "defect", "damage"):
        assert word not in head.lower()


def test_headline_names_instrumentation_when_that_is_the_real_problem():
    channels = [chan(index=2, artefacts=["Mains pickup: 50 Hz at 37x."]),
                chan(index=7, artefacts=["Mains pickup: 50 Hz at 34x."])]
    c = ctx(running=False, channels=channels)
    findings = [f for rule in RULES for f in rule(c)]
    head = _headline(c, findings)
    assert "mains interference" in head
    assert "2 channel" in head


def test_headline_on_a_clean_running_machine_says_so_plainly():
    c = ctx(running=True, channels=[chan(index=0, threshold_status={"rms": "within limit 0.01"})])
    findings = [f for rule in RULES for f in rule(c)]
    head = _headline(c, findings)
    assert "running" in head.lower()
    assert "no measured value is outside its limit" in head
