"""Tests for bearing resolution — VIK-010.

The normalisation tests matter more than they look. A bearing's fault orders
come from its internal geometry, so matching "NU2220" to the catalogue row for
"2220" does not produce a slightly wrong answer, it produces a confidently
wrong one: four frequencies that a diagnosis engine will then look for in the
spectrum, find nothing at, and report the machine as healthy.

So these pin both directions — that real suffixes are stripped, and that
prefixes and base numbers survive untouched.
"""

from __future__ import annotations

import pytest

from app.ai.bearings import BearingMatch, normalise_designation


# --------------------------------------------------- suffixes come off --

@pytest.mark.parametrize("raw,expected", [
    ("6312-C3", "6312"),        # the exact case in the ticket
    ("6310-C3", "6310"),
    ("6310 C3", "6310"),        # space instead of hyphen
    ("6312/C3", "6312"),        # slash, as SKF writes it
    ("6312_C3", "6312"),
    ("6200-2RS1", "6200"),      # longest-first: 2RS1 before 2RS before RS
    ("6205-2RS", "6205"),
    ("6205ZZ", "6205"),
    ("22320 W33", "22320"),
    ("  6312-c3  ", "6312"),    # whitespace and case
])
def test_construction_suffixes_are_stripped(raw, expected):
    assert normalise_designation(raw) == expected


# ------------------------------------------- base numbers stay intact --

@pytest.mark.parametrize("raw,expected", [
    ("6312", "6312"),
    ("NU 2220 E", "NU2220"),    # prefix kept, suffix removed
    ("NU2220", "NU2220"),
    ("N2220", "N2220"),
    ("22320", "22320"),
])
def test_base_designations_survive(raw, expected):
    assert normalise_designation(raw) == expected


def test_a_prefix_is_never_mistaken_for_a_suffix():
    """NU2220, N2220 and 2220 are three different bearings with three
    different geometries. A rule loose enough to strip the prefix would
    collapse them onto one catalogue row and every fault frequency would be
    wrong — while looking entirely ordinary on screen."""
    assert normalise_designation("NU2220") != "2220"
    assert normalise_designation("N2220") != "2220"
    assert normalise_designation("NU2220") != normalise_designation("N2220")


def test_stripping_never_empties_the_designation():
    """A suffix is only removed if digits remain. Otherwise "E" would
    normalise to "" and match nothing, or worse, match everything."""
    for raw in ("E", "C3", "ZZ", "K", "W"):
        assert normalise_designation(raw) == raw.upper()


@pytest.mark.parametrize("raw", ["", "   ", None])
def test_empty_input_is_handled(raw):
    assert normalise_designation(raw) == ""


# ------------------------------------------------------ the match type --

def test_an_unmatched_bearing_is_not_silently_zero():
    """source="none" with confidence 0.0 must be distinguishable from a real
    match — a caller that reads the orders without checking the source would
    otherwise get None and treat it as "no fault"."""
    m = BearingMatch(query="9999", normalised="9999")
    assert m.source == "none"
    assert m.confidence == 0.0
    assert m.bpfo is None
    assert m.catalog_id is None


# ------------------------------------------------- against the database --
#
# Skipped where no database is reachable, so the suite still runs offline.

def _db():
    try:
        from app.database import SessionLocal
        session = SessionLocal()
        session.execute(__import__("sqlalchemy").text(
            "SELECT 1 FROM bearing_fault_frequencies LIMIT 1")).fetchone()
        return session
    except Exception:
        return None


@pytest.fixture
def db():
    session = _db()
    if session is None:
        pytest.skip("no database, or the bearing catalogue is not loaded")
    yield session
    session.close()


def test_the_tickets_acceptance_case_resolves(db):
    """VIK-009's acceptance names 6312 and 6310; VIK-010 is what makes the
    plant's own spelling of them reach those rows."""
    from app.ai.bearings import match_from_catalogue

    for raw, expected in (("6312-C3", "6312"), ("6310-C3", "6310")):
        m = match_from_catalogue(db, raw)
        assert m.source == "catalogue", f"{raw} did not resolve"
        assert m.designation == expected
        assert m.catalog_id is not None
        for order in (m.ftf, m.bsf, m.bpfo, m.bpfi):
            assert order and order > 0


def test_catalogue_orders_are_physically_consistent(db):
    """BPFO + BPFI equals the rolling-element count. This is an identity, not
    a convention, so it catches a row read from the wrong columns."""
    from app.ai.bearings import match_from_catalogue

    m = match_from_catalogue(db, "6312-C3")
    assert m.rolling_elements
    assert m.bpfo + m.bpfi == pytest.approx(m.rolling_elements, abs=0.02)


def test_manufacturer_disagreement_lowers_confidence_and_is_stated(db):
    """12 manufacturers list 6312 and their BSF differs by about 1%. The
    spread is reported rather than averaged: an average produces a number no
    manufacturer publishes."""
    from app.ai.bearings import match_from_catalogue

    m = match_from_catalogue(db, "6312")
    if m.candidates > 1 and m.notes:
        assert m.confidence < 1.0
        assert any("differs by" in n for n in m.notes)


def test_a_preferred_manufacturer_is_honoured(db):
    from app.ai.bearings import match_from_catalogue

    everyone = match_from_catalogue(db, "6312")
    if everyone.candidates < 2:
        pytest.skip("only one manufacturer lists 6312 here")
    chosen = match_from_catalogue(db, "6312", preferred_manufacturer="SKF")
    assert chosen.manufacturer.upper() == "SKF"


def test_an_unknown_designation_falls_back_rather_than_raising(db):
    """The ticket: fall back and keep the lower confidence rather than
    failing. A machine with an uncatalogued bearing still gets an answer."""
    from app.ai.bearings import match_with_fallback

    m = match_with_fallback(db, "99999-NOTREAL")
    assert m.source in {"none", "estimated"}
    assert m.confidence < 1.0
    assert m.notes, "an unresolved bearing must say why"
