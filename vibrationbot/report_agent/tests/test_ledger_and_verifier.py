"""Adversarial tests for the fact ledger and the report verifier.

This is the guarantee the whole report agent rests on: no number reaches a
report unless it was recorded first, with a source. Until now it had no tests.

The verifier has already been wrong once, in a way that matters more than the
bug itself. The first version ran its checks *after* substituting ledger values
into the text. At that point every legitimate figure is a bare digit in the
prose, so the bare-number check would have flagged the ledger's own output --
and to avoid that it was written loosely enough to flag nothing at all. It
passed every report forever while appearing to work.

So these tests care about two things in particular:

* the check must FIRE on a hand-typed number, and
* it must NOT fire on a ledger value that arrived legitimately.

Getting only the first right gives a verifier nobody can use. Getting only the
second gives one that protects nothing.
"""

from __future__ import annotations

import pytest

from report_agent.ledger import Ledger, Provenance
from report_agent.render import Rendered, verify


@pytest.fixture
def ledger() -> Ledger:
    led = Ledger()
    led.measured("worst RMS", 0.42409, "scaled_eng", "channel 3, capture f88e67ab")
    led.computed("shaft speed", 1500, "rpm", "platform FFT estimate")
    return led


# ----------------------------------------------------------------- ledger --


def test_a_fact_carries_its_provenance(ledger):
    fact = ledger.get("F1")
    assert fact.provenance is Provenance.MEASURED
    assert fact.source, "a fact with no source defeats the point of the ledger"


def test_substitution_replaces_the_placeholder_with_the_value(ledger):
    text, missing = ledger.substitute("The worst reading was {{F1}}.")
    assert "0.42409 scaled_eng" in text
    assert missing == []


def test_a_placeholder_with_no_fact_is_reported_not_silently_dropped(ledger):
    text, missing = ledger.substitute("A confident {{F99}} appears here.")
    assert missing == ["F99"]
    assert "{{F99}}" in text, "an unresolved reference must stay visible, not vanish"


# ------------------------------------------------------- bare-number check --


def test_a_hand_typed_number_in_narrative_is_caught(ledger):
    """The guard must fire. This is the entire purpose of the ledger."""
    raw = "## 1. Summary\n\nVibration reached 47.3 mm/s at the drive end.\n"
    result = verify(ledger, Rendered(text=raw, raw=raw))

    assert not result.ok, "a number nobody recorded passed verification"
    assert "47.3" in result.bare_numbers
    assert any("BARE NUMBER" in p for p in result.problems())


def test_a_legitimate_ledger_value_is_not_flagged(ledger):
    """The other half. A verifier that rejects correct reports is unusable.

    The narrative references {{F1}}; after substitution the text contains
    '0.42409'. Checking the substituted text would flag the ledger's own value
    -- which is exactly how the original bug arose.
    """
    raw = "## 1. Summary\n\nThe worst reading was {{F1}}.\n"
    text, _ = ledger.substitute(raw)
    result = verify(ledger, Rendered(text=text, raw=raw))

    assert result.ok, f"a ledger value was wrongly flagged: {result.problems()}"
    assert result.bare_numbers == []


def test_checking_the_substituted_text_would_have_flagged_the_ledger_value(ledger):
    """Pins the original bug in place so it cannot return unnoticed.

    Passing the substituted text as BOTH halves is what the broken version
    effectively did. If some future change makes this pass, the verifier has
    stopped distinguishing a recorded value from a typed one.
    """
    raw = "## 1. Summary\n\nThe worst reading was {{F1}}.\n"
    text, _ = ledger.substitute(raw)

    wrong_way = verify(ledger, Rendered(text=text, raw=text))

    assert not wrong_way.ok, (
        "checking substituted text no longer flags anything -- the bare-number "
        "check has been loosened to the point of being useless"
    )


def test_an_unresolved_placeholder_blocks_the_report(ledger):
    text = "## 1. Summary\n\nThe reading was {{F99}}.\n"
    result = verify(ledger, Rendered(text=text, raw=text))

    assert not result.ok
    assert "F99" in result.unresolved


def test_a_reference_to_a_fact_that_was_never_registered_is_caught(ledger):
    raw = "## 1. Summary\n\nSee {{F42}} for detail.\n"
    result = verify(ledger, Rendered(text=raw, raw=raw))
    assert "F42" in result.unknown_refs


# ------------------------------------------------ scope of the prose check --


def test_numbers_inside_a_table_are_not_flagged(ledger):
    """Table cells are where ledger values belong. Flagging them would make
    the check noise, and noise gets switched off."""
    raw = "## 1. Summary\n\n| Feature | Value |\n|---|---|\n| RMS | 0.42409 |\n"
    assert verify(ledger, Rendered(text=raw, raw=raw)).ok


def test_numbers_outside_the_narrative_section_are_not_flagged(ledger):
    """Only prose a model writes is checked. The provenance appendix is all
    digits by design."""
    raw = "## 6. Provenance\n\nF1 measured 0.42409 scaled_eng on channel 3.\n"
    assert verify(ledger, Rendered(text=raw, raw=raw)).ok


def test_an_empty_ledger_says_the_report_asserts_nothing():
    result = verify(Ledger(), Rendered(text="## 1. Summary\n\nNothing.\n",
                                       raw="## 1. Summary\n\nNothing.\n"))
    assert any("asserts nothing" in n for n in result.notes)


@pytest.mark.parametrize("phrase", ["a 1X component", "the 2X harmonic"])
def test_order_notation_is_language_not_a_measurement(ledger, phrase):
    raw = f"## 1. Summary\n\nEnergy appears at {phrase} of shaft speed.\n"
    assert verify(ledger, Rendered(text=raw, raw=raw)).ok, (
        f"{phrase!r} was treated as a hand-typed figure"
    )
