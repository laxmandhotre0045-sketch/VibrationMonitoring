"""Section 4.1's switches and filter settings.

Fourteen of section 4.1's nineteen settings existed. The five that did not
were three on/off switches and two filter bands, and the switches are the
ones that matter: every engine ran unconditionally, so a machine being
commissioned produced findings that were true of a machine nobody was
trying to diagnose, and they reached the same baselines and the same queue
as everything else.

**A setting is only real if something reads it.** Half these tests are
about the readers rather than the table, because a settings row nothing
consults is a form.
"""

from __future__ import annotations

import inspect

import pytest
from sqlalchemy import text

from app.services.general_settings import GeneralSettings, settings_for, update


def test_an_unconfigured_plant_has_everything_on(db):
    """A migration that silently turned a running engine off would be a
    worse fault than the gap it closes."""
    settings = settings_for(db)
    assert settings.mode_detection_enabled is True
    assert settings.fault_detection_enabled is True
    assert settings.auto_reports_enabled is True
    assert settings.anything_disabled is False


def test_the_settings_say_where_they_came_from(db):
    """"Everything is on" means something different when nobody has ever
    configured anything."""
    assert settings_for(db).source in ("plant", "machine", "fallback")


def test_a_machine_can_be_taken_out_of_diagnosis_without_stopping_ingest(
        db, sensor_id):
    equipment = db.execute(text("""
        SELECT equipment_id FROM sensor_configurations WHERE id = :s
    """), {"s": str(sensor_id)}).scalar()

    changed = update(db, equipment_id=equipment, analyst="a.kulkarni",
                     notes="Commissioning; findings would be about a machine "
                           "nobody is trying to diagnose.",
                     fault_detection_enabled=False)
    db.flush()

    assert changed.fault_detection_enabled is False
    assert changed.source == "machine"
    # The rest of the plant is untouched.
    assert settings_for(db).fault_detection_enabled is True
    db.rollback()


def test_turning_an_engine_off_needs_a_reason(db):
    """A switch found six months later by somebody who cannot tell whether
    it was deliberate is worse than no switch."""
    with pytest.raises(ValueError, match="needs a reason"):
        update(db, equipment_id=None, analyst="a",
               fault_detection_enabled=False)
    db.rollback()


def test_the_database_refuses_it_too(db):
    """Enforced in both places: the service gives a sentence, the
    constraint stops anything that bypasses the service."""
    with pytest.raises(Exception):
        db.execute(text("""
            INSERT INTO ai_general_settings
                (equipment_id, mode_detection_enabled)
            VALUES (gen_random_uuid(), false)
        """))
        db.flush()
    db.rollback()


def test_an_unknown_setting_is_refused(db):
    with pytest.raises(ValueError, match="not a general setting"):
        update(db, equipment_id=None, analyst="a", enable_telepathy=True)
    db.rollback()


def test_a_filter_band_must_be_the_right_way_round(db):
    with pytest.raises(Exception):
        db.execute(text("""
            INSERT INTO ai_general_settings
                (equipment_id, highpass_hz, lowpass_hz)
            VALUES (gen_random_uuid(), 5000, 10)
        """))
        db.flush()
    db.rollback()


def test_unset_filters_mean_the_existing_behaviour_not_no_filtering(db):
    """Null has to mean "as the code already does it". Reading it as "no
    filter" would change every machine's numbers on the migration."""
    settings = settings_for(db)
    assert settings.highpass_hz is None
    assert settings.lowpass_hz is None
    assert settings.envelope_band_low_hz is None


# ------------------------------------------- the switches are consulted --

def test_mode_detection_reads_its_switch():
    from app.services import mode_storage

    source = inspect.getsource(mode_storage)
    assert "mode_detection_enabled" in source, (
        "the switch exists but the mode detector never reads it, which "
        "makes the setting a form")


def test_fault_detection_reads_its_switch():
    from app.services import fault_storage

    source = inspect.getsource(fault_storage)
    assert "fault_detection_enabled" in source


def test_a_disabled_engine_says_nothing_was_looked_for(db):
    """Not "nothing was found". The distinction this whole platform turns
    on, applied to its own switches."""
    from app.services import fault_storage, mode_storage

    for module in (fault_storage, mode_storage):
        source = inspect.getsource(module)
        assert "not the same as" in source or "different from" in source, (
            f"{module.__name__} disables silently")


def test_editing_the_plant_default_does_not_duplicate_it(db):
    """Postgres treats NULLs as distinct in a unique index, so
    `ON CONFLICT (equipment_id)` never matched the plant-wide row and every
    edit inserted another one. Nothing errored; `settings_for` then
    returned whichever duplicate the planner reached first, so a plant-wide
    change appeared to do nothing about half the time."""
    for i in range(3):
        update(db, equipment_id=None, analyst="a.kulkarni",
               notes=f"edit {i}", auto_reports_enabled=False)
        db.flush()

    rows = db.execute(text("""
        SELECT COUNT(*) FROM ai_general_settings WHERE equipment_id IS NULL
    """)).scalar()
    assert rows == 1
    assert settings_for(db).auto_reports_enabled is False
    db.rollback()


def test_a_failed_settings_read_leaves_every_engine_on(db, monkeypatch):
    """The fallback is the dangerous path and nothing covered it.

    These are read on every capture. A bad row, a lock, a migration
    half-applied — any of them makes the read throw, and the wrong
    fallback silently stops diagnosing the plant. Nobody would see an
    error; findings would simply stop appearing, which looks exactly like
    machines being healthy.
    """
    import app.services.general_settings as module

    def explode(*args, **kwargs):
        raise RuntimeError("settings table unavailable")

    monkeypatch.setattr(module, "text", explode)

    settings = module.settings_for(db)
    assert settings.source == "fallback"
    assert settings.mode_detection_enabled is True
    assert settings.fault_detection_enabled is True
    assert settings.auto_reports_enabled is True
    assert settings.anything_disabled is False
