"""Tests for the question-answering bot — MOM item 5.

Refusal is the behaviour under test. A bot over measurement data is asked
things the data cannot answer far more often than things it can, and the
failure that costs money is a confident wrong answer, not a missing one.

These exercise the paths that do not need a network. The model call itself is
stubbed, so a run without an API key tests the same logic as a run with one.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services import ai_bot, llm
from app.services.ai_analysis import Analysis, Finding
from app.services.ai_bot import MAX_QUESTION_CHARS, ask


def finding(**kw) -> Finding:
    base = dict(code="c", title="Machine is not running",
                detail="loudest is 0.02376 g against an idle ceiling of 0.0244 g",
                severity="informational", confidence="high")
    base.update(kw)
    return Finding(**base)


ANALYSIS = Analysis(
    generated_at=datetime.now(timezone.utc),
    headline="The machine is stopped.",
    findings=[finding()],
    cannot_conclude=["Whether the machine has a fault. The machine is not turning."],
    context_summary={"machine_name": "Pump 1", "machine_running": False},
)


@pytest.fixture
def stub(monkeypatch):
    """Replace the analysis and the model, so no database or network is used."""
    monkeypatch.setattr(ai_bot.ai_analysis, "analyse", lambda db, sid=None: ANALYSIS)

    def set_reply(text, configured=True):
        monkeypatch.setattr(ai_bot.llm, "is_configured", lambda: configured)
        monkeypatch.setattr(ai_bot.llm, "model_name", lambda: "gpt-4o-mini")
        monkeypatch.setattr(ai_bot.llm, "complete",
                            lambda *a, **k: text)
    return set_reply


# ----------------------------------------------------------- input guards --

def test_an_empty_question_is_refused_without_calling_the_model(stub):
    stub("should never be used")
    a = ask(None, "   ")
    assert a.source == "refused"
    assert a.refused_reason == "empty question"


def test_an_overlong_question_is_refused(stub):
    stub("should never be used")
    a = ask(None, "x" * (MAX_QUESTION_CHARS + 1))
    assert a.source == "refused"
    assert "too long" in a.refused_reason


# ------------------------------------------------------------ no model --

def test_without_a_model_the_bot_says_so_rather_than_failing(stub):
    stub(None, configured=False)
    a = ask(None, "Is the pump healthy?")
    assert a.source == "unavailable"
    assert "No language model is configured" in a.answer
    # the findings are still worth pointing at
    assert a.grounded_on


# ------------------------------------------------------ the verification --

def test_an_answer_with_an_invented_number_is_withheld(stub):
    """The failure this exists for. 4.7 mm/s appears in no finding, so the
    answer is not shown at all -- there is no template for an arbitrary
    question, so a failed check ends in refusal rather than fallback."""
    stub("Vibration is 4.7 mm/s RMS, which is Zone C.")
    a = ask(None, "How bad is it?")
    assert a.source == "refused"
    assert "4.7" in a.refused_reason
    assert "4.7" not in a.answer


def test_an_answer_using_only_measured_numbers_is_returned(stub):
    stub("The loudest channel reads 0.02376 g, below the 0.0244 g idle ceiling.")
    a = ask(None, "What is the level?")
    assert a.source == "model"
    assert "0.02376" in a.answer


def test_a_model_outage_is_reported_not_faked(stub):
    stub(None, configured=True)
    a = ask(None, "Is the pump healthy?")
    assert a.source == "refused"
    assert "could not be reached" in a.answer


# ------------------------------------------------------------- grounding --

def test_the_evidence_the_answer_was_allowed_is_returned(stub):
    """So a reader can check the answer rather than trust it."""
    stub("The machine is stopped.")
    a = ask(None, "What is happening?")
    assert any("Machine is not running" in e for e in a.grounded_on)
    assert any("cannot answer" in e for e in a.grounded_on)


def test_the_question_is_echoed_back_for_the_transcript(stub):
    stub("The machine is stopped.")
    a = ask(None, "What is happening?")
    assert a.question == "What is happening?"
