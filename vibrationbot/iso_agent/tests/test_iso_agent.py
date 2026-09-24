"""The ISO agent, and the separation that is the point of it existing.

The interesting tests here are not that a lookup returns a number -- the
domain library is already tested for that. They are that this agent is
genuinely independent of the knowledge-base agent, and that the questions a
model used to get wrong now go through code instead.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from vibcore import iso10816
from iso_agent.agent import ASKS_LIMIT_RE, answer, parse_question

#: These tests spawn a fresh interpreter, which does not inherit pytest's
#: sys.path. Without an explicit working directory they fail whenever the
#: suite is invoked from anywhere but vibrationbot/ -- three false failures
#: that look exactly like a real regression.
PACKAGE_ROOT = Path(__file__).resolve().parent.parent.parent


def _in_fresh_interpreter(code: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, cwd=str(PACKAGE_ROOT),
    )


# ------------------------------------------------------------- separation --


def test_iso_agent_does_not_import_the_knowledge_base_agent():
    """The whole reason this package exists: it must stand alone.

    Run in a fresh interpreter, because this test session has almost certainly
    imported kb_agent already and would pass for the wrong reason.
    """
    code = (
        "import sys, iso_agent; "
        "leaked=[m for m in sys.modules if m.startswith('kb_agent')]; "
        "print('LEAK' if leaked else 'CLEAN')"
    )
    out = _in_fresh_interpreter(code)
    assert "CLEAN" in out.stdout, f"iso_agent pulled in kb_agent: {out.stdout} {out.stderr}"


def test_iso_agent_loads_no_search_stack():
    """No faiss, no embedding model. This agent reads a table."""
    code = (
        "import sys, iso_agent; "
        "heavy=[m for m in sys.modules if m.split('.')[0] in "
        "{'faiss','torch','sentence_transformers'}]; "
        "print('HEAVY' if heavy else 'LIGHT')"
    )
    out = _in_fresh_interpreter(code)
    assert "LIGHT" in out.stdout, f"search stack loaded: {out.stdout} {out.stderr}"


def test_answering_needs_no_api_key():
    """No model takes part, so no key is required and nothing is billed."""
    code = (
        "import os; os.environ.pop('OPENAI_API_KEY', None); "
        "import iso_agent; "
        "print('OK' if iso_agent.answer('zone B/C for a 55 kW pump, "
        "separate driver, rigid').ok else 'FAILED')"
    )
    out = _in_fresh_interpreter(code)
    assert "OK" in out.stdout, out.stdout + out.stderr


# ------------------------------------------------------------------ parse --


@pytest.mark.parametrize(
    "question, field, expected",
    [
        ("limit for a 55 kW pump", "power_kw", 55.0),
        ("limit for a 1.5 MW motor", "power_kw", 1500.0),
        ("vibration limit for a 100 hp fan", "power_kw", 74.57),
        ("zone boundary for a pump on a rigid foundation", "foundation", "rigid"),
        ("zone boundary, flexible support", "foundation", "flexible"),
        ("55 kW pump with integrated driver", "integrated_driver", True),
        ("55 kW pump with separate driver", "integrated_driver", False),
        ("is 4.9 mm/s acceptable", "reading_mm_s", 4.9),
    ],
)
def test_question_parsing(question, field, expected):
    value = getattr(parse_question(question), field)
    if isinstance(expected, float):
        assert value == pytest.approx(expected, rel=1e-3)
    else:
        assert value == expected


# ----------------------------------------------------------------- answer --


#: Boundaries are READ FROM THE STANDARD'S OWN TABLE, never retyped here.
#:
#: This is the lesson of the whole ISO episode. The evaluation harness once
#: hardcoded "a 55 kW pump is Group 2, so rigid B/C is 2,8 mm/s" -- wrong, and
#: wrong in exactly the way the agent was, so neither caught the other. A test
#: that restates a rule can restate it incorrectly.
#:
#: The transcription is pinned once, against the published standard, by
#: BOUNDARY_MATRIX in tests/test_domain_iso.py. Everything downstream derives
#: from it, so a test here cannot disagree with the source of truth.
_TABLE = json.loads(
    (Path(iso10816.__file__).parent / "data" / "iso10816_3.json").read_text(encoding="utf-8")
)["velocity_rms_mm_s"]


def boundary(group: int, support: str, which: str) -> float:
    """One boundary, from the standard's table. A/B, B/C or C/D."""
    return _TABLE[str(group)][support][["A/B", "B/C", "C/D"].index(which)]


def test_pump_group_is_by_driver_not_power():
    """The defect that started all of this.

    ISO 10816-3 puts pumps in Group 3 or Group 4 by DRIVER ARRANGEMENT, not by
    rated power. Groups 1 and 2 are power-banded and contain no pumps. Asked
    for a 55 kW pump a model read the Group 1/2 tables and reported 2.8; the
    correct answer for a separate driver on a rigid foundation is Group 3's.
    """
    result = answer("zone B/C for a 55 kW pump with a separate driver, rigid foundation")
    assert result.ok
    assert f"{boundary(3, 'rigid', 'B/C')} mm/s" in result.text
    assert "Group 3" in result.text


def test_power_does_not_move_a_pump_out_of_its_group():
    """The precise misreading, pinned. A pump at any power is Group 3 or 4.

    5 kW, 55 kW and 5 MW must all give the same answer. If rated power ever
    starts selecting the group again, exactly this test fails.
    """
    answers = [answer(f"zone B/C for a {p} pump with a separate driver, rigid foundation")
               for p in ("5 kW", "55 kW", "5 MW")]
    assert all(r.ok for r in answers)
    expected = f"{boundary(3, 'rigid', 'B/C')} mm/s"
    for r, p in zip(answers, ("5 kW", "55 kW", "5 MW")):
        assert "Group 3" in r.text, f"{p} pump was not Group 3"
        assert expected in r.text, f"{p} pump gave a different boundary"


def test_the_group_1_and_2_boundaries_are_not_used_for_a_pump():
    """Groups 1 and 3 share a table, as do 2 and 4, which is what made the
    original error hard to see. The check that matters is the group named."""
    result = answer("zone B/C for a 55 kW pump with a separate driver, rigid foundation")
    assert "Group 1" not in result.text and "Group 2" not in result.text


def test_unstated_driver_reports_both_groups_rather_than_guessing():
    result = answer("what is the vibration limit for a 55 kW pump")
    assert result.ok
    assert "Group 3" in result.text and "Group 4" in result.text
    assert f"{boundary(3, 'rigid', 'A/B')} mm/s" in result.text
    assert f"{boundary(4, 'rigid', 'A/B')} mm/s" in result.text


def test_reading_is_graded_against_the_right_table():
    """4.9 mm/s sits above the 4.5 B/C boundary and below 7.1 C/D -> Zone C."""
    result = answer("is 4.9 mm/s acceptable on a 55 kW pump, separate driver, rigid?")
    assert result.ok
    assert "Zone C" in result.text


def test_value_exactly_on_a_boundary_takes_the_lower_zone():
    """The standard's convention, and the opposite of a naive comparison."""
    result = answer("is 4.5 mm/s acceptable on a 55 kW pump, separate driver, rigid?")
    assert result.ok
    assert "falls in Zone B" in result.text


def test_missing_details_are_named_not_silently_assumed():
    result = answer("vibration limit for a pump")
    assert result.ok
    assert "Not stated in the question" in result.text


@pytest.mark.parametrize(
    "question",
    [
        "what is the zone B/C boundary for a pump",
        "is 4.9 mm/s acceptable",
        "what is the acceptable vibration limit",
        "ISO 10816-3 zone limits in mm/s",
    ],
)
def test_limit_questions_are_recognised(question):
    assert ASKS_LIMIT_RE.search(question)


@pytest.mark.parametrize(
    "question",
    ["what causes oil whirl", "explain time synchronous averaging"],
)
def test_explanatory_questions_are_not_claimed_by_this_agent(question):
    assert not ASKS_LIMIT_RE.search(question)


# ------------------------------------------------------- staying in scope --
#
# Before this, "what is wrong with the big pump downstairs" returned a full set
# of boundary tables, because the question contains the word "pump". Correct
# numbers, to a question nobody asked. An agent that answers outside its
# subject is a quieter form of the failure this one exists to prevent.


@pytest.mark.parametrize(
    "question",
    [
        "what is wrong with the big pump downstairs",
        "why is the pump making a noise",
        "how do I align a pump coupling",
        "what causes cavitation in a centrifugal pump",
    ],
)
def test_a_question_that_is_not_about_limits_is_declined(question):
    result = answer(question)
    assert not result.ok, f"answered an off-topic question: {question!r}"
    assert "kb_agent" in result.reason, "declined without saying where to go instead"


def test_the_decline_does_not_leak_a_limit():
    """A refusal that still prints the tables has refused nothing."""
    result = answer("what is wrong with the big pump downstairs")
    assert result.text == ""
    for value in ("2.3", "4.5", "7.1", "1.4", "2.8"):
        assert value not in result.reason


@pytest.mark.parametrize(
    "question",
    [
        "zone B/C for a 55 kW pump, separate driver, rigid",
        "is 4.9 mm/s acceptable on a 75 kW pump",
        "what is the acceptable vibration limit for a 55 kW motor",
    ],
)
def test_real_limits_questions_are_still_answered(question):
    assert answer(question).ok, f"declined a genuine limits question: {question!r}"


def test_an_underspecified_limits_question_asks_rather_than_declining():
    """Two different refusals, and they must not be confused.

    "vibration limit for a motor" IS a limits question -- it just cannot be
    resolved, because motors are grouped by rated power and none was given.
    That deserves "tell me the power", not "wrong agent, go to the librarian".
    Pumps differ: they are grouped by driver arrangement, so a pump with no
    power still resolves to Groups 3 and 4.
    """
    result = answer("what is the acceptable vibration limit for a motor")
    assert not result.ok
    assert "kb_agent" not in result.reason, "sent a genuine limits question away"
    assert "power" in result.reason.lower(), "did not say what was missing"
