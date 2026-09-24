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
    """12 manufacturers list 6312 and their BSF differs by 1.2%. The spread is
    reported rather than averaged: an average produces a number no
    manufacturer publishes.

    This assertion used to sit behind `if m.candidates > 1 and m.notes:`,
    which meant that switching the disagreement check off emptied `notes` and
    the test passed by skipping itself. Mutation testing found it. The
    catalogue is a fixed spreadsheet, so the counts are pinned outright.
    """
    from app.ai.bearings import match_from_catalogue

    m = match_from_catalogue(db, "6312")
    assert m.candidates == 12, (
        f"{m.candidates} rows for 6312; the import may have run twice"
    )
    assert m.confidence == pytest.approx(0.85)
    assert len(m.notes) == 1, m.notes
    assert "BSF differs by 1.2%" in m.notes[0]
    assert "FAF is used" in m.notes[0]


def test_a_large_disagreement_is_reported_on_every_order_that_shows_it(db):
    """6205 is the case that matters. Its manufacturers differ by 13.7% on
    BPFO -- enough to move a bearing peak by a whole spectrum line at this
    machine's speed -- and all four orders disagree. One note per order, so
    the reader sees which ones.
    """
    from app.ai.bearings import match_from_catalogue

    m = match_from_catalogue(db, "6205")
    assert len(m.notes) == 4, m.notes
    assert m.confidence < 1.0
    joined = " ".join(m.notes)
    for order in ("FTF", "BSF", "BPFO", "BPFI"):
        assert f"{order} differs by" in joined
    assert "BPFO differs by 13.7%" in joined


def test_the_orders_returned_are_one_manufacturers_and_not_an_average(db):
    """The whole point of reporting the spread instead of smoothing it. The
    numbers handed downstream must be a row someone actually publishes."""
    from app.ai.bearings import match_from_catalogue
    from sqlalchemy import text

    m = match_from_catalogue(db, "6205")
    rows = db.execute(text(
        "select manufacturer, ftf, bsf, bpfo, bpfi from bearing_fault_frequencies "
        "where designation = '6205'")).fetchall()
    published = {(r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4])) for r in rows}
    assert (m.manufacturer, m.ftf, m.bsf, m.bpfo, m.bpfi) in published


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


# ---------------------------------------- more gaps mutation testing found --

def test_an_empty_designation_never_reaches_the_database():
    """A blank bearing field on an equipment record is common. Looking it up
    is a full-table scan that can only return the wrong bearing."""
    from app.ai.bearings import match_from_catalogue

    class Exploding:
        def execute(self, *a, **k):
            raise AssertionError("the database was queried for an empty designation")

    for blank in ("", "   ", None, "-", "/"):
        m = match_from_catalogue(Exploding(), blank)
        assert m.source == "none"
        assert m.catalog_id is None


def test_disagreement_is_measured_against_the_larger_value():
    """A percentage needs a stated base. Against the smaller value every
    spread reads higher than it is, and the 1% tolerance then trips on
    rounding differences that mean nothing."""
    from app.ai.bearings import _spread

    assert _spread([3.0, 3.1]) == pytest.approx(0.1 / 3.1, rel=1e-9)
    assert _spread([3.0, 3.1]) < 0.1 / 3.0
    assert _spread([2.0]) == 0.0
    assert _spread([]) == 0.0
    assert _spread([0.0, 0.0]) == 0.0


def test_the_suffix_list_is_closed_and_does_not_strip_unknown_letters():
    """A general "drop trailing letters" rule would collapse different
    bearings onto one catalogue row, each then carrying the wrong fault
    orders with nothing on screen to say so. Only listed suffixes go."""
    from app.ai.bearings import normalise_designation

    # listed suffixes are removed
    assert normalise_designation("6312-C3") == "6312"
    assert normalise_designation("6205-2RS1") == "6205"
    assert normalise_designation("22220 W33") == "22220"

    # an unlisted trailing letter is not
    assert normalise_designation("6312XY") == "6312XY"

    # and prefixes are never touched, which is where the collapse would happen
    assert normalise_designation("NU2220") == "NU2220"
    assert normalise_designation("N2220") == "N2220"
    assert normalise_designation("NU2220") != normalise_designation("N2220")
