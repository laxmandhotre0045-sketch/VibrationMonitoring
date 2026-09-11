"""The ISO agent, and the separation that is the point of it existing.

The interesting tests here are not that a lookup returns a number -- the
domain library is already tested for that. They are that this agent is
genuinely independent of the knowledge-base agent, and that the questions a
model used to get wrong now go through code instead.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from iso_agent.agent import ASKS_LIMIT_RE, answer, parse_question


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
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert "CLEAN" in out.stdout, f"iso_agent pulled in kb_agent: {out.stdout} {out.stderr}"


def test_iso_agent_loads_no_search_stack():
    """No faiss, no embedding model. This agent reads a table."""
    code = (
        "import sys, iso_agent; "
        "heavy=[m for m in sys.modules if m.split('.')[0] in "
        "{'faiss','torch','sentence_transformers'}]; "
        "print('HEAVY' if heavy else 'LIGHT')"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert "LIGHT" in out.stdout, f"search stack loaded: {out.stdout} {out.stderr}"


def test_answering_needs_no_api_key():
    """No model takes part, so no key is required and nothing is billed."""
    code = (
        "import os; os.environ.pop('OPENAI_API_KEY', None); "
        "import iso_agent; "
        "print('OK' if iso_agent.answer('zone B/C for a 55 kW pump, "
        "separate driver, rigid').ok else 'FAILED')"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
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


def test_pump_group_is_by_driver_not_power():
    """The defect that started all of this.

    ISO 10816-3 puts pumps in Group 3 or Group 4 by driver arrangement, not by
    rated power. A model reading the document reported 2.8 for both. The Group
    3 rigid B/C boundary is 4.5.
    """
    result = answer("zone B/C for a 55 kW pump with a separate driver, rigid foundation")
    assert result.ok
    assert "4.5 mm/s" in result.text
    assert "Group 3" in result.text


def test_unstated_driver_reports_both_groups_rather_than_guessing():
    result = answer("what is the vibration limit for a 55 kW pump")
    assert result.ok
    assert "Group 3" in result.text and "Group 4" in result.text
    assert "2.3 mm/s" in result.text and "1.4 mm/s" in result.text


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
