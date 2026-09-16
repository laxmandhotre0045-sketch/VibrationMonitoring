"""Adversarial tests for the five output guards.

These guards are the only thing standing between a model's prose and a wrong
number in front of an engineer, and until now not one of them had a test.

Every test here feeds a guard the exact input it exists to catch. That
direction matters more than the happy path: this project has already shipped
two checks that could not fail -- a verifier that ran after substitution, and a
narrative extractor that matched no headings -- and both looked like they were
working. A guard is not proven by passing clean input. It is proven by
rejecting dirty input.

Each test names the real observed failure it is defending against, so that
anyone tempted to relax a rule can see what it cost when it was absent.
"""

from __future__ import annotations

import pytest

from kb_agent.agent import (
    _annotate_equations,
    _check_standard_attribution,
    _enforce_verbatim_equations,
    _flag_scoped_limits,
    _refer_limits_to_iso_agent,
)


def _excerpt(text: str, **kw):
    base = {"text": text, "doc_id": "cat2", "chunk_id": "c1", "page_start": 1}
    base.update(kw)
    return base


# ------------------------------------------------- verbatim equation guard --
#
# Observed: over five runs the model quoted the damaged BPFO equation unaltered
# twice and "repaired" it three times -- restoring the fraction bar while
# dropping the divide-by-two, which doubles every value computed from it.


def test_rewritten_equation_is_replaced_with_the_source_text():
    """The guard must fire. This is the whole reason it exists."""
    excerpts = [_excerpt("BPFO = n/2 * (1 - d/D * cos(a)) * rpm")]
    answer = "The outer race frequency is BPFO = n * (1 - d/D * cos(a)) * rpm."

    fixed, corrected = _enforce_verbatim_equations(answer, excerpts)

    assert corrected == ["BPFO"], "the guard did not notice the rewrite"
    assert "n/2" in fixed, "the source's divide-by-two was not restored"
    assert "BPFO = n * (1 -" not in fixed, "the model's version survived"


def test_an_equation_quoted_correctly_is_left_alone():
    """A guard that rewrites correct text is its own kind of bug."""
    excerpts = [_excerpt("BPFO = n/2 * (1 - d/D * cos(a)) * rpm")]
    answer = "The formula is BPFO = n/2 * (1 - d/D * cos(a)) * rpm."

    fixed, corrected = _enforce_verbatim_equations(answer, excerpts)

    assert corrected == []
    assert fixed == answer


def test_an_equation_with_no_matching_source_is_not_invented():
    """Nothing to compare against means nothing to correct -- not a guess."""
    excerpts = [_excerpt("Some prose with no equations in it at all.")]
    answer = "The formula is BSF = D/d * (1 - (d/D)**2) * rpm."

    fixed, corrected = _enforce_verbatim_equations(answer, excerpts)

    assert corrected == []
    assert fixed == answer


def test_empty_answer_does_not_crash_the_guard():
    assert _enforce_verbatim_equations("", [_excerpt("BPFO = n/2 * x")]) == ("", [])


# -------------------------------------------- standard attribution guard --
#
# Observed: a passage reading "The API specification on vibration limits..."
# was reported as "API 610 specifies ... for centrifugal pumps". The source
# names neither the part number nor the machine type. "API 610" appears
# nowhere in the corpus.


def test_a_part_number_no_source_states_is_flagged():
    """The guard must fire. A part number selects which limits apply."""
    excerpts = [_excerpt("The API specification covers vibration limits for turbo machines.")]
    answer = "API 610 specifies a vibration limit for centrifugal pumps."

    flagged, unsupported = _check_standard_attribution(answer, excerpts)

    assert unsupported == ["API 610"], "an invented part number went unnoticed"
    assert "WARNING" in flagged
    assert "unverified" in flagged


def test_a_part_number_the_source_does_state_is_accepted():
    excerpts = [_excerpt("ISO 10816-3 defines evaluation zones for this machine class.")]
    answer = "ISO 10816 defines the evaluation zones."

    flagged, unsupported = _check_standard_attribution(answer, excerpts)

    assert unsupported == []
    assert flagged == answer


@pytest.mark.parametrize("source_form", ["ISO 10816", "ISO10816", "ISO-10816"])
def test_the_source_may_punctuate_the_number_however_it_likes(source_form):
    """Extraction mangles spacing; the guard must not fire on formatting."""
    excerpts = [_excerpt(f"{source_form} sets the boundaries.")]
    flagged, unsupported = _check_standard_attribution("ISO 10816 sets them.", excerpts)
    assert unsupported == [], f"false alarm on source spelled {source_form!r}"


# ------------------------------------------------------ scoped limit guard --
#
# Observed: choosing the right row of a scoped severity table was measured at
# 1 correct in 5 -- worse than a coin, while reading as authoritative.


def test_a_limit_pinned_to_a_rated_machine_is_flagged():
    answer = "For that machine the Zone B/C boundary is 4.5 mm/s."
    out = _flag_scoped_limits(answer, "what is the limit for a 55 kW pump")
    assert out != answer, "a scoped limit was stated with no warning attached"
    assert "iso_agent" in out, "the warning does not say where the right answer lives"


def test_the_warning_is_not_stacked_twice():
    answer = "Zone B/C is 4.5 mm/s. See python -m iso_agent for the authoritative value."
    assert _flag_scoped_limits(answer, "limit for a 55 kW pump") == answer


def test_an_unrated_question_is_left_alone():
    """No machine rating in the question means no row was being selected."""
    answer = "Zone B is defined as acceptable for long-term operation."
    assert _flag_scoped_limits(answer, "what does zone B mean") == answer


# ----------------------------------------------------------- iso referral --


def test_a_limit_question_gets_told_where_the_number_lives():
    out = _refer_limits_to_iso_agent("Zones are defined by the standard.",
                                     "what is the zone B/C boundary for a pump")
    assert "iso_agent" in out


def test_the_referral_is_not_repeated():
    answer = 'Ask python -m iso_agent "<your question>" for the number.'
    assert _refer_limits_to_iso_agent(answer, "zone B/C boundary for a pump") == answer


def test_an_explanatory_question_gets_no_referral():
    answer = "Oil whirl is a sub-synchronous instability."
    assert _refer_limits_to_iso_agent(answer, "what causes oil whirl") == answer


# --------------------------------------------------------- equation caveat --


def test_a_quoted_equation_carries_the_extraction_caveat():
    excerpts = [_excerpt("BPFO = n/2 * (1 - d/D) * rpm")]
    out = _annotate_equations("The formula is BPFO = n/2 * (1 - d/D) * rpm.", excerpts)
    assert out != "The formula is BPFO = n/2 * (1 - d/D) * rpm.", (
        "an equation was quoted with no note that PDF extraction damages them"
    )


def test_prose_with_no_equation_is_left_alone():
    excerpts = [_excerpt("Unbalance produces a once-per-revolution force.")]
    answer = "Unbalance produces a once-per-revolution force."
    assert _annotate_equations(answer, excerpts) == answer


# ------------------------------------------------------------- warm-up --
#
# The warm-up is an optimisation, so the thing worth testing is that it can
# never change an answer or raise: it must be safe to call twice, and safe
# when a model cannot load at all.


def test_warm_models_is_safe_to_call_repeatedly():
    from kb_agent import library
    library.warm_models()
    library.warm_models()          # must not start a second pair of threads


def test_warm_models_never_raises_when_a_model_cannot_load(monkeypatch):
    """A failed warm-up must stay silent and let the real call report the error
    where the caller can see it, not from a background thread."""
    import threading
    from kb_agent import library

    monkeypatch.setattr(library, "_WARM_STARTED", False)
    started: list[threading.Thread] = []
    real_thread = threading.Thread

    def capture(*a, **kw):
        t = real_thread(*a, **kw)
        started.append(t)
        return t

    monkeypatch.setattr(library.threading, "Thread", capture)
    monkeypatch.setitem(
        __import__("sys").modules, "app.retrieval.embeddings", None
    )  # make the import inside the thread fail

    library.warm_models()          # must not raise here
    for t in started:
        t.join(timeout=10)         # nor inside the threads
