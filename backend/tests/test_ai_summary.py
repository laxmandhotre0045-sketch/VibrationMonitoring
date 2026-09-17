"""Tests for the summary verifier — MOM item 6.

The generated prose is the only part of this platform a language model writes,
and a number is the easiest thing for it to drift. The verifier exists to catch
exactly that, so these tests are mostly about what it REJECTS.

A verifier that cannot reject is the failure this project has shipped before:
a check that ran after the substitution it was meant to police, and a narrative
extractor that matched no headings. Both looked like they worked.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.ai_analysis import Analysis, Finding
from app.services.ai_summary import (
    _grounded_numbers,
    _split,
    _template,
    _ungrounded,
)


def finding(**kw) -> Finding:
    base = dict(code="c", title="t", detail="d", severity="warning",
                confidence="high")
    base.update(kw)
    return Finding(**base)


def analysis(findings, headline="Headline.", running=False, cannot=None) -> Analysis:
    return Analysis(
        generated_at=datetime.now(timezone.utc),
        headline=headline,
        findings=findings,
        cannot_conclude=cannot or [],
        context_summary={"machine_name": "Cooling Water Pump 1",
                         "machine_running": running},
    )


# ---------------------------------------------------------- the verifier --

def test_a_number_that_appears_in_a_finding_is_accepted():
    f = [finding(detail="50 Hz line at 56x the noise floor.")]
    allowed = _grounded_numbers(f, extra=[])
    assert _ungrounded("The 50 Hz line reaches 56x.", allowed) == []


def test_a_number_that_appears_nowhere_is_rejected():
    """The failure this exists for: a plausible figure never measured."""
    f = [finding(detail="50 Hz line at 56x the noise floor.")]
    allowed = _grounded_numbers(f, extra=[])
    bad = _ungrounded("Vibration reached 4.7 mm/s RMS.", allowed)
    assert "4.7" in bad


def test_a_rounding_of_a_measured_value_is_accepted():
    """0.02 from a measured 0.0244 is the model rounding what it was given."""
    f = [finding(detail="idle ceiling of 0.0244 g")]
    allowed = _grounded_numbers(f, extra=[])
    assert _ungrounded("about 0.02 g", allowed) == []


def test_added_precision_is_rejected():
    """The reverse of rounding. Given 0.02, writing 0.0244 invents digits."""
    f = [finding(detail="a limit of 0.02 g")]
    allowed = _grounded_numbers(f, extra=[])
    assert "0.0244" in _ungrounded("measured 0.0244 g", allowed)


def test_small_counting_numbers_are_not_treated_as_measurements():
    """'the 2 channels' must not be rejected for lack of a measurement."""
    allowed = _grounded_numbers([finding(detail="no numbers here")], extra=[])
    assert _ungrounded("Both of the 2 channels are affected.", allowed) == []


def test_numbers_from_the_headline_and_caveats_count_as_grounded():
    f = [finding(detail="d", caveat="needs 17 h before a trend means anything")]
    allowed = _grounded_numbers(f, extra=["1.4 h of the 7-day window"])
    assert _ungrounded("only 1.4 h of 7 days, and 17 h are needed", allowed) == []


def test_evidence_values_count_as_grounded():
    f = [finding(detail="d", evidence={"ac_rms_g": 0.02376})]
    allowed = _grounded_numbers(f, extra=[])
    assert _ungrounded("0.02376 g", allowed) == []


# ------------------------------------------------------------- splitting --

def test_suggestions_are_separated_from_prose():
    prose, sugg = _split("The pump is stopped.\n\n- Fix the grounding.\n- Re-measure.")
    assert prose == "The pump is stopped."
    assert sugg == ["Fix the grounding.", "Re-measure."]


def test_bullet_variants_are_all_recognised():
    _, sugg = _split("x\n- a\n* b\n• c")
    assert sugg == ["a", "b", "c"]


# -------------------------------------------------------------- template --

def test_the_template_is_usable_on_its_own():
    """On a deployment with no API key this IS the summary, permanently — so
    it has to say something, not stand in for something."""
    a = analysis([
        finding(title="ch2: electrical interference, not vibration",
                caveat="Fix the screening or grounding."),
        finding(title="No 7-day trend yet", severity="informational"),
    ], headline="The machine is stopped.", running=False)
    prose, suggestions = _template(a)
    assert "The machine is stopped." in prose
    assert "ch2" in prose
    assert "mechanical condition" in prose      # the idle caveat survives
    assert any("grounding" in s for s in suggestions)
    assert any("running" in s for s in suggestions)


def test_the_template_does_not_invent_a_fault_on_an_idle_machine():
    a = analysis([finding(title="Machine is not running", severity="informational")],
                 headline="The machine is stopped.", running=False)
    prose, _ = _template(a)
    for word in ("fault", "failure", "damage", "defect"):
        assert word not in prose.lower()


def test_the_template_lists_at_most_three_suggestions():
    a = analysis([finding(title=f"f{i}", caveat=f"do thing {i}") for i in range(6)],
                 running=True)
    _, suggestions = _template(a)
    assert len(suggestions) <= 3
