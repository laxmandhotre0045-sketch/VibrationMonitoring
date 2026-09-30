"""Which condition the machine was running in — VIK-039.

The ticket's rule is one sentence: "a capture with no clear mode is
labelled unknown, never forced into the nearest one". Most of this file is
that sentence, tested from every direction it can be broken from, because
forcing is the tempting mistake and it is silent. A capture pushed into the
wrong mode joins that mode's baseline, widens its spread, and the next real
fault sits comfortably inside the widened normal.

The other half is about what the engine is allowed to believe. The shaft
speed estimator returns a number even when it could not establish one --
the tallest line in the spectrum, which on this pump is four times the true
speed. Banding on that would place every capture in a mode with full
confidence and be wrong every time.
"""

from __future__ import annotations

import pytest

from app.ai.operating_mode import (
    EDGE_CONFIDENCE,
    MIN_CONFIDENCE,
    OFF,
    OFF_LEVEL_G,
    UNKNOWN,
    ModeBand,
    detect_mode,
)

LOW = ModeBand("m-low", "low_load", 1200.0, 1400.0)
HIGH = ModeBand("m-high", "high_load", 1450.0, 1550.0)
BANDS = [LOW, HIGH]

RUNNING = 0.01           # a normal running level in g
RPM = lambda r: r / 60.0  # noqa: E731 - rpm to Hz, used constantly below


def detect(rpm=1500.0, *, bands=None, usable=True, level=RUNNING, **kw):
    return detect_mode(BANDS if bands is None else bands,
                       shaft_hz=RPM(rpm) if rpm is not None else None,
                       shaft_usable=usable, overall_level_g=level, **kw)


# ------------------------------------------------ a clear match --------

def test_a_capture_in_the_middle_of_a_band_is_that_mode():
    verdict = detect(1500.0)
    assert verdict.label == "high_load"
    assert verdict.mode_id == "m-high"
    assert verdict.is_unknown is False
    assert verdict.confidence == 1.0


def test_confidence_falls_towards_the_edge_of_a_band():
    """A capture on a boundary genuinely could be either side. Reporting it
    as certain hides a real ambiguity from whoever reads the finding."""
    middle = detect(1500.0).confidence
    edge = detect(1550.0).confidence
    assert middle == 1.0
    assert edge == pytest.approx(EDGE_CONFIDENCE)
    assert edge < middle


def test_an_open_ended_band_never_claims_certainty():
    """"Anything above 1450 rpm" is a legitimate band with no centre, so
    nothing inside it can be called a central fit."""
    open_band = [ModeBand("m", "high_load", 1450.0, None)]
    assert detect(9000.0, bands=open_band).confidence == pytest.approx(
        EDGE_CONFIDENCE)


# ------------------------------------------- unknown, never forced -----

def test_a_speed_outside_every_band_is_unknown_not_the_nearest():
    """The ticket's rule. 1425 rpm sits between the two bands, 25 rpm from
    one and 25 from the other -- exactly the case where taking the nearest
    is most tempting."""
    verdict = detect(1425.0)
    assert verdict.label == UNKNOWN
    assert verdict.is_unknown is True
    assert verdict.mode_id is None
    assert verdict.confidence == 0.0
    assert "nearest" in verdict.reason


def test_a_machine_with_no_configured_modes_reports_every_capture_unknown():
    """Not a failure. The engine cannot invent what load the machine was
    under, and defaulting to "normal running" would be exactly that."""
    verdict = detect(1500.0, bands=[])
    assert verdict.label == UNKNOWN
    assert "No operating modes are configured" in verdict.reason


def test_a_band_with_no_bounds_is_not_a_catch_all():
    """A row with neither end set matches everything and would make every
    other band unreachable. Treated as unusable rather than as a default."""
    verdict = detect(1500.0, bands=[ModeBand("m", "normal_running")])
    assert verdict.label == UNKNOWN


def test_an_unusable_shaft_speed_is_treated_as_no_speed():
    """The estimator returns 97.21 Hz on this pump when it cannot establish
    a speed -- four times the true one. Banding on that would place every
    capture confidently in the wrong mode."""
    verdict = detect(None, usable=False)
    assert verdict.label == UNKNOWN
    assert "could not be established" in verdict.reason

    # The case that matters: a number that would land squarely inside a band
    # if it were believed. An earlier version of this test used a speed
    # outside every band, so it passed whether the usable flag was honoured
    # or not.
    verdict = detect(1500.0, usable=False)
    assert verdict.label == UNKNOWN, (
        "1500 rpm sits in the middle of high_load, so believing an unusable "
        "speed would place this capture there with full confidence"
    )
    assert "could not be established" in verdict.reason


def test_a_match_too_weak_to_act_on_is_unknown():
    """A band technically containing the capture is not enough on its own.

    At the centre, the instability penalty still leaves a usable match. At
    the edge it does not, and the capture is left unassigned rather than
    counted towards a mode it only barely matched.
    """
    narrow = [ModeBand("m", "high_load", 1450.0, 1550.0)]

    centre = detect_mode(narrow, shaft_hz=RPM(1500.0), shaft_usable=True,
                         overall_level_g=RUNNING, stability="unstable")
    assert centre.confidence == pytest.approx(0.5)
    assert centre.is_unknown is False

    edge = detect_mode(narrow, shaft_hz=RPM(1550.0), shaft_usable=True,
                       overall_level_g=RUNNING, stability="unstable")
    assert edge.label == UNKNOWN, (
        f"the edge of the band, halved for an unstable speed, is "
        f"{EDGE_CONFIDENCE * 0.5} -- below the {MIN_CONFIDENCE} floor"
    )
    assert edge.is_unknown is True
    assert str(MIN_CONFIDENCE) in edge.reason


# ------------------------------------------------------- stopped -------

def test_a_stopped_machine_is_off_without_anybody_configuring_it():
    """"Off" is the one mode nobody bothers to write down, and it is
    decidable from the signal: no vibration and no shaft speed."""
    verdict = detect(None, usable=False, level=OFF_LEVEL_G / 10)
    assert verdict.label == OFF
    assert verdict.is_unknown is False
    assert verdict.confidence == 1.0


def test_a_quiet_but_turning_machine_is_not_off():
    """Level alone would call a healthy machine on a very quiet mounting
    stopped, and then exclude it from its own baseline."""
    verdict = detect(1500.0, level=OFF_LEVEL_G / 10)
    assert verdict.label != OFF


# ------------------------------------------- what it reports back ------

def test_an_unstable_speed_lowers_confidence_and_says_so():
    """A baseline built from captures whose speed was moving describes a
    machine that was never at one speed."""
    steady = detect(1500.0, stability="steady")
    moving = detect(1500.0, stability="unstable")
    assert moving.confidence < steady.confidence
    assert "unstable" in moving.reason


def test_overlapping_bands_are_reported_rather_than_silently_resolved():
    """Two bands containing the same speed is a configuration problem, and
    the person who can fix it has to be able to see it."""
    overlapping = [ModeBand("a", "low_load", 1400.0, 1600.0),
                   ModeBand("b", "high_load", 1450.0, 1550.0)]
    verdict = detect_mode(overlapping, shaft_hz=RPM(1500.0),
                          shaft_usable=True, overall_level_g=RUNNING)
    assert verdict.is_unknown is False
    assert verdict.candidates, "the losing band must be recorded"
    assert "other band" in verdict.reason


def test_every_verdict_explains_itself():
    """A mode decides which baseline a capture joins, so a wrong one has to
    be traceable to the reason it was made."""
    for verdict in (detect(1500.0), detect(1425.0), detect(None, usable=False),
                    detect(1500.0, bands=[])):
        assert verdict.reason, f"{verdict.label} gave no reason"
        assert len(verdict.reason) > 40


def test_the_evidence_travels_with_the_verdict():
    verdict = detect(1500.0, stability="steady")
    payload = verdict.as_dict()
    assert payload["shaft_hz"] == pytest.approx(25.0)
    assert payload["overall_level"] == RUNNING
    assert payload["stability"] == "steady"


# ------------------------------- section 6.1's transient states ----------

def test_a_machine_coming_up_to_speed_is_not_filed_as_a_steady_band():
    """The reason these needed adding at all.

    A machine on its way up passes through every band below its target. A
    matcher that compares one capture against a static range files that ramp
    as a steady state and then averages it into that mode's baseline —
    which is exactly the contamination this module exists to prevent.
    """
    from app.ai.operating_mode import STARTUP

    band = ModeBand("m", "normal_running", 1400.0, 1550.0)
    verdict = detect_mode([band], shaft_hz=RPM(1480.0), shaft_usable=True,
                          overall_level_g=RUNNING, stability="steady",
                          previous_shaft_hz=RPM(700.0))

    assert verdict.label == STARTUP
    assert verdict.is_unknown is False
    assert "coming up to speed" in verdict.reason


def test_a_machine_running_down_is_told_from_one_coming_up():
    """Nothing looking at a single capture can separate these: the same
    700 rpm on the way up and on the way down."""
    from app.ai.operating_mode import SHUTDOWN, STARTUP

    band = ModeBand("m", "normal_running", 1400.0, 1550.0)
    rising = detect_mode([band], shaft_hz=RPM(700.0), shaft_usable=True,
                         overall_level_g=RUNNING, stability="steady",
                         previous_shaft_hz=RPM(300.0))
    falling = detect_mode([band], shaft_hz=RPM(700.0), shaft_usable=True,
                          overall_level_g=RUNNING, stability="steady",
                          previous_shaft_hz=RPM(1480.0))

    assert rising.label == STARTUP
    assert falling.label == SHUTDOWN


def test_ordinary_speed_regulation_is_not_a_ramp():
    """A loaded machine's speed wanders by a couple of per cent. Calling
    that a startup would put most captures in a transient state."""
    band = ModeBand("m", "normal_running", 1400.0, 1550.0)
    verdict = detect_mode([band], shaft_hz=RPM(1490.0), shaft_usable=True,
                          overall_level_g=RUNNING, stability="steady",
                          previous_shaft_hz=RPM(1470.0))
    assert verdict.label == "normal_running"


def test_speed_moving_within_the_capture_is_its_own_mode():
    from app.ai.operating_mode import VARIABLE_SPEED

    band = ModeBand("m", "high_load", 1450.0, 1550.0)
    verdict = detect_mode([band], shaft_hz=RPM(1500.0), shaft_usable=True,
                          overall_level_g=RUNNING, stability="variable",
                          previous_shaft_hz=RPM(1500.0))
    assert verdict.label == VARIABLE_SPEED
    assert "smeared" in verdict.reason


def test_variable_speed_and_unstable_operation_stay_separate():
    """Section 6.1 lists both. An unstable capture still matches its band
    and carries a reduced confidence — "high load, and shakily" — rather
    than having the band discarded."""
    from app.ai.operating_mode import VARIABLE_SPEED

    band = ModeBand("m", "high_load", 1450.0, 1550.0)
    unstable = detect_mode([band], shaft_hz=RPM(1500.0), shaft_usable=True,
                           overall_level_g=RUNNING, stability="unstable",
                           previous_shaft_hz=RPM(1500.0))
    assert unstable.label == "high_load"
    assert unstable.label != VARIABLE_SPEED
    assert unstable.confidence < 1.0


def test_a_machine_turning_but_not_working_is_idling():
    from app.ai.operating_mode import IDLE

    band = ModeBand("m", "normal_running", 1400.0, 1550.0)
    verdict = detect_mode([band], shaft_hz=RPM(400.0), shaft_usable=True,
                          overall_level_g=RUNNING, stability="steady",
                          previous_shaft_hz=RPM(400.0),
                          rated_shaft_hz=RPM(1480.0))
    assert verdict.label == IDLE
    assert "not doing its job" in verdict.reason


def test_idle_needs_a_rated_speed_to_compare_against():
    """Without one there is no "slow for this machine", only a number."""
    band = ModeBand("m", "normal_running", 1400.0, 1550.0)
    verdict = detect_mode([band], shaft_hz=RPM(400.0), shaft_usable=True,
                          overall_level_g=RUNNING, stability="steady",
                          previous_shaft_hz=RPM(400.0))
    assert verdict.label != "idle"


def test_a_transient_state_is_decided_before_the_bands():
    """Otherwise a ramp matches whichever band it is passing through."""
    import inspect

    from app.ai import operating_mode

    source = inspect.getsource(operating_mode.detect_mode)
    assert source.index("STARTUP") < source.index("usable = [b for b in bands")
