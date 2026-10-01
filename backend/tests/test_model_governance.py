"""Model governance — section 22.

Section 22 lists nine things to store and ends with the line that gives
them their point: "No model should be changed silently without version
tracking."

**That line is the test.** Everything else here is schema; the guard below
is the requirement. It compares what the code is running against what the
registry has heard of, so bumping a version without recording what changed
fails the suite. It is deliberately the same shape as the released-revision
manifest that guards the migration chain — both protect a promise about
history, and no amount of inspecting the current state can verify one of
those.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.ai.versions import BY_KEY, COMPONENTS, version_of
from app.services.governance import (
    model_performance,
    register,
    registry,
    summary,
    unregistered,
)

NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)


# ------------------------------------------- the line section 22 ends on --

def test_no_running_version_is_unregistered(db):
    """The guard. A version the code stamps on its output and the registry
    has never heard of is exactly a model that changed silently."""
    gaps = unregistered(db)
    assert not gaps, (
        f"these running versions are not in the registry: {gaps}. Register "
        f"what changed, or the stored rows they stamp cannot be explained.")


def test_the_registry_reports_whether_it_is_being_honoured(db):
    report = summary(db)
    assert report["compliant"] is True
    assert report["reason"]


def test_a_bumped_version_is_caught(db, monkeypatch):
    """Proving the guard bites rather than merely passing.

    Without this, `test_no_running_version_is_unregistered` would pass just
    as happily if `unregistered` always returned an empty list.
    """
    import app.services.governance as governance

    bumped = tuple(
        type(c)(c.key, c.name, "99" if c.key == "fault" else c.version,
                c.stamps)
        for c in COMPONENTS)
    monkeypatch.setattr(governance, "COMPONENTS", bumped)

    assert "fault v99" in governance.unregistered(db)


# ------------------------------------- one declaration, not five copies --

def test_every_service_reads_its_version_from_the_one_declaration():
    """Five modules each holding their own constant is five places to
    forget."""
    from app.services import (
        anomaly_storage,
        detector_storage,
        fault_storage,
        mode_storage,
        quality_storage,
    )

    for key, module in (("anomaly", anomaly_storage),
                        ("detectors", detector_storage),
                        ("fault", fault_storage),
                        ("operating_mode", mode_storage),
                        ("quality", quality_storage)):
        assert module.ENGINE_VERSION == version_of(key), key


def test_the_two_versions_that_did_not_exist_before_now_do():
    """Feature extraction and processing had no version at all, so a change
    to how a feature is computed was indistinguishable from a change in the
    machine -- every stored value would shift and nothing would say why."""
    assert "feature_extraction" in BY_KEY
    assert "processing" in BY_KEY


def test_every_component_says_what_its_version_stamps():
    """A version number nobody can look up is a string. `stamps` is what
    tells a reader which stored rows become incomparable when it changes."""
    for component in COMPONENTS:
        assert component.stamps, component.key
        assert len(component.stamps) > 20, component.key


# ---------------------------------------------------- what is recorded ---

def test_the_registry_holds_section_22s_fields(db):
    columns = {r[0] for r in db.execute(text("""
        SELECT column_name FROM information_schema.columns
         WHERE table_name = 'model_versions'
    """)).fetchall()}

    required = {
        "version": "model version",
        "trained_at": "training date",
        "training_period_start": "training data period",
        "training_period_end": "training data period",
        "performance": "model performance",
        "superseded_by": "rollback option",
        "notes": "what changed",
    }
    missing = {c: label for c, label in required.items() if c not in columns}
    assert not missing, f"section 22 fields not stored: {missing}"


def test_a_version_cannot_be_registered_without_saying_what_changed(db):
    """A version number with no account of what changed is a string."""
    with pytest.raises(ValueError, match="what changed"):
        register(db, component="fault", version="2", notes="   ")


def test_an_unknown_component_is_refused(db):
    with pytest.raises(ValueError, match="not a declared component"):
        register(db, component="astrology", version="1", notes="x")


def test_registering_supersedes_the_previous_version_rather_than_deleting(db):
    """The rows the old version stamped are still in the database and still
    need explaining."""
    before = [r for r in registry(db) if r["component"] == "anomaly"]
    assert any(r["superseded_at"] is None for r in before)

    register(db, component="anomaly", version="2",
             notes="Widened the sigma anchors after the first month of data.",
             trained_at=NOW, training_period_start=NOW - timedelta(days=90),
             training_period_end=NOW, trained_on_captures=4000)
    db.flush()

    after = [r for r in registry(db) if r["component"] == "anomaly"]
    assert len(after) == len(before) + 1

    old = [r for r in after if r["version"] == "1"][0]
    assert old["superseded_at"] is not None
    assert old["superseded_by"] == "2"

    new = [r for r in after if r["version"] == "2"][0]
    assert new["superseded_at"] is None
    assert new["trained_on_captures"] == 4000
    db.rollback()


def test_a_superseded_row_must_name_its_successor(db):
    """Otherwise the rollback path is a dead end."""
    with pytest.raises(Exception):
        db.execute(text("""
            INSERT INTO model_versions (component, name, version,
                                        superseded_at)
            VALUES ('fault', 'Fault diagnosis', 'x', now())
        """))
        db.flush()
    db.rollback()


# -------------------------------------------------------- performance ---

def test_performance_is_unmeasured_rather_than_perfect_without_feedback(db):
    """A model nobody has judged has no measured performance, which is a
    different statement from performing badly."""
    db.execute(text("DELETE FROM analyst_feedback"))
    db.flush()

    measured = model_performance(db, "fault")
    assert measured["measured"] is False
    assert measured["precision"] is None
    assert "not the same as performing badly" in measured["reason"]
    db.rollback()


def test_components_nobody_judges_say_so_rather_than_reporting_a_score(db):
    verdict = model_performance(db, "processing")
    assert verdict["measured"] is False
    assert "unmeasured" in verdict["reason"]
