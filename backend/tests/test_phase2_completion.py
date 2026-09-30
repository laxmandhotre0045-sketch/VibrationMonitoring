"""The Phase 2 items that were specified and never built.

Phase 2 was the one phase never audited line by line against the document.
It turned out to be missing seventeen of sixty-seven items — more than any
other phase — which is what auditing against ticket status rather than
against the requirement costs.

These cover the pieces added to close it: section 21.1's remaining data
quality checks, section 6.1's transient operating modes, section 11.2's
mode discovery, and section 4.2's last two Expert Mode settings.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.ai.alarm import resolve
from app.ai.quality import (
    MIN_DISTINCT_VALUES,
    check_delivery,
    _check_low_signal,
    _check_wrong_machine_state,
    _check_wrong_rpm,
    _check_sensor_temperature,
)


# ---------------------------------------- 21.1: the checks that were not --

def test_a_signal_made_of_a_dozen_values_is_called_low_signal():
    """The check that describes this gateway, and it did not exist. The
    pump's channels hold twelve to seventy-three distinct values across a
    whole record, so most of the spectrum is the converter rounding."""
    step = 5.0 / 32768 / 0.100
    rng = np.random.default_rng(3)
    gateway = np.round(rng.normal(0, 0.0032, 13888) / step) * step

    verdict = _check_low_signal(gateway, 50.0)
    assert verdict.passed is False
    assert verdict.value < MIN_DISTINCT_VALUES
    assert "converter rounding" in verdict.reason


def test_a_healthy_signal_is_not_called_low():
    """A first version also tested amplitude against the converter range at
    0.1% and graded a perfectly healthy 0.036 g signal as poor — because
    this hardware's range is ±50 g, so healthy *is* 0.07% of it."""
    rng = np.random.default_rng(0)
    healthy = 0.05 * np.sin(np.linspace(0, 400, 50_000)) + \
        0.005 * rng.normal(size=50_000)
    assert _check_low_signal(healthy, 50.0).passed is True


def test_a_speed_that_cannot_be_right_is_flagged():
    """Not a speed that is unusual — a VFD legitimately runs far from
    nameplate. This catches the estimator locking onto the wrong peak, and
    if it did then every order in the diagnosis is wrong by that ratio."""
    assert _check_wrong_rpm(24.67, 1480.0).passed is True
    assert _check_wrong_rpm(49.34, 1480.0).passed is False


def test_speed_cannot_be_judged_without_a_rated_speed():
    verdict = _check_wrong_rpm(24.67, None)
    assert verdict.applicable is False


def test_a_capture_tagged_running_from_a_stopped_machine_is_caught():
    """It poisons the baseline it feeds and nothing downstream can tell
    afterwards."""
    still = np.zeros(4096)
    assert _check_wrong_machine_state(still, "running", 50.0).passed is False


def test_machine_state_cannot_be_judged_without_a_tag():
    rng = np.random.default_rng(1)
    moving = rng.normal(0, 0.05, 4096)
    assert _check_wrong_machine_state(moving, None, 50.0).applicable is False


def test_the_temperature_check_exists_and_says_it_cannot_run():
    """Section 21.1 asks for it and nothing here measures one. A check
    that is silently absent reads as a check that passed."""
    verdict = _check_sensor_temperature(None)
    assert verdict.applicable is False
    assert "no temperature is measured" in verdict.reason.lower()


def test_a_gateway_that_goes_silent_is_noticed():
    """This one has gone quiet for days at a time and nothing anywhere
    noticed. Delivery is a property of how captures arrived, which is why
    it was missing — every other check takes a sample array."""
    gaps = [125.0] * 200 + [101 * 3600.0]
    checks = {c.name: c for c in check_delivery(gaps, 125.0)}

    assert checks["packet_loss"].passed is False
    assert checks["communication"].passed is False
    assert "link was down" in checks["communication"].reason


def test_steady_delivery_passes():
    checks = {c.name: c for c in check_delivery([125.0] * 200, 125.0)}
    assert all(c.passed for c in checks.values())


def test_delivery_cannot_be_judged_from_one_capture():
    for check in check_delivery([]):
        assert check.applicable is False


# ------------------------------------------- 4.2: Expert Mode's last two --

def test_expert_mode_can_scope_alarms_to_chosen_bands():
    """Without it a plant whose gearbox mesh always looks alarming has two
    options people actually take: raise the threshold until nothing rings,
    or ignore the screen."""
    expert = resolve("expert", {"frequency_bands": ["envelope",
                                                    "crest_factor"]})
    assert expert.covers("envelope_rms") is True
    assert expert.covers("crest_factor") is True
    assert expert.covers("amplitude_1x") is False


def test_no_band_scoping_means_everything_is_in_scope():
    assert resolve("balanced").covers("anything") is True


def test_expert_mode_can_loosen_mode_separation():
    assert resolve("balanced").mode_separation == "strict"
    assert resolve("expert",
                   {"mode_separation": "loose"}).mode_separation == "loose"


def test_an_unrecognised_setting_does_not_silently_widen_the_comparison():
    """Falling back to 'loose' on a typo would compare a reading against
    the machine's whole history without anybody asking for it."""
    assert resolve("expert",
                   {"mode_separation": "whatever"}).mode_separation == "strict"
    assert resolve("expert", {"frequency_bands": "notalist"}
                   ).frequency_bands == ()


def test_the_expert_settings_survive_construction():
    """They were validated, put in a dict, and then dropped — the object
    was built positionally from the four settings that already existed."""
    expert = resolve("expert", {"mode_separation": "loose",
                                "frequency_bands": ["envelope"],
                                "score_threshold": 70})
    assert expert.mode_separation == "loose"
    assert expert.frequency_bands == ("envelope",)
    assert expert.score_threshold == 70.0
