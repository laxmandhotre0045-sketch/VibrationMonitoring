"""Acceleration to velocity — VIK-007.

Two clauses in the acceptance: a known sine converts within 1%, and there is
no second integrator in the codebase. The second is the one that needs a test,
because it is the one that decays: a second integrator is never added
deliberately, it is added by someone who needs velocity, does not find it, and
writes four lines that look obviously correct.

They drift because the parts that make integration correct are not the
division by omega. They are the integration floor, the band mask and the
near-DC handling, and those have to agree between orders. Keeping two copies
in step by hand is how they stop being in step.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest

from app.services.casing_orbit import (
    G_TO_MS2,
    acceleration_to_displacement_um,
    acceleration_to_velocity_mm_s,
    integration_floor_hz,
    velocity_mm_s_from_acceleration_g,
)

FS = 5000.0
SHAFT_HZ = 25.0


def sine(freq_hz: float, amplitude_g: float = 1.0, seconds: float = 2.0):
    t = np.arange(0, seconds, 1.0 / FS)
    return amplitude_g * np.sin(2.0 * np.pi * freq_hz * t)


def theory_velocity_rms_mm_s(freq_hz: float, amplitude_g: float = 1.0) -> float:
    """v_peak = a_peak / (2*pi*f), then peak -> rms for a sine."""
    peak_mm_s = (amplitude_g * G_TO_MS2) / (2.0 * np.pi * freq_hz) * 1000.0
    return peak_mm_s / np.sqrt(2.0)


# ------------------------------------------------ the acceptance clause --

@pytest.mark.parametrize("freq_hz", [25.0, 50.0, 100.0, 300.0])
def test_a_known_sine_converts_within_one_percent(freq_hz):
    velocity = acceleration_to_velocity_mm_s(
        sine(freq_hz), FS, floor_hz=integration_floor_hz(SHAFT_HZ)
    )
    measured = float(np.sqrt(np.mean(velocity ** 2)))
    expected = theory_velocity_rms_mm_s(freq_hz)
    assert measured == pytest.approx(expected, rel=0.01)


def test_velocity_falls_as_one_over_frequency():
    """The physical relation, not just one point. Doubling the frequency at
    the same acceleration halves the velocity -- a sign error or a squared
    term passes a single-frequency check and fails this."""
    low = float(np.sqrt(np.mean(acceleration_to_velocity_mm_s(
        sine(50.0), FS, floor_hz=integration_floor_hz(SHAFT_HZ)) ** 2)))
    high = float(np.sqrt(np.mean(acceleration_to_velocity_mm_s(
        sine(100.0), FS, floor_hz=integration_floor_hz(SHAFT_HZ)) ** 2)))
    assert low / high == pytest.approx(2.0, rel=0.01)


def test_the_scalar_form_agrees_with_the_array_form():
    """Two entry points, one answer. If they disagree, one of them is the
    second integrator this ticket exists to prevent."""
    peak_from_scalar = velocity_mm_s_from_acceleration_g(1.0, 50.0)
    array_rms = float(np.sqrt(np.mean(acceleration_to_velocity_mm_s(
        sine(50.0), FS, floor_hz=integration_floor_hz(SHAFT_HZ)) ** 2)))
    assert peak_from_scalar / np.sqrt(2.0) == pytest.approx(array_rms, rel=0.01)


# ----------------------------------------------- the floor still applies --

def test_content_below_the_integration_floor_is_rejected():
    """Integration divides by f, so a 0.5 Hz bin is amplified fifty times
    relative to a 25 Hz one. Without the floor, near-DC drift dominates the
    answer and the velocity describes the drift rather than the machine."""
    floor = integration_floor_hz(SHAFT_HZ)
    assert floor > 0.5
    below = acceleration_to_velocity_mm_s(sine(0.5), FS, floor_hz=floor)
    assert float(np.sqrt(np.mean(below ** 2))) < 1e-6


def test_the_floor_tracks_the_shaft_speed():
    """A quarter of shaft rate, never below the absolute minimum."""
    assert integration_floor_hz(100.0) == pytest.approx(25.0)
    assert integration_floor_hz(1.0) == pytest.approx(2.0)   # absolute minimum


def test_a_band_mask_excludes_what_it_should():
    inside = acceleration_to_velocity_mm_s(
        sine(50.0), FS, lower_hz=40.0, upper_hz=60.0,
        floor_hz=integration_floor_hz(SHAFT_HZ))
    outside = acceleration_to_velocity_mm_s(
        sine(50.0), FS, lower_hz=200.0, upper_hz=400.0,
        floor_hz=integration_floor_hz(SHAFT_HZ))
    assert float(np.sqrt(np.mean(inside ** 2))) > 1.0
    assert float(np.sqrt(np.mean(outside ** 2))) < 1e-6


# --------------------------------------- displacement must not regress --

def test_displacement_is_unchanged_by_the_generalisation():
    """Order 2 went through the same refactor. x = a / (2*pi*f)^2."""
    freq = 50.0
    got = float(np.sqrt(np.mean(acceleration_to_displacement_um(
        sine(freq), FS, lower_hz=None, upper_hz=None,
        floor_hz=integration_floor_hz(SHAFT_HZ)) ** 2)))
    expected = (G_TO_MS2 / (2.0 * np.pi * freq) ** 2 * 1e6) / np.sqrt(2.0)
    assert got == pytest.approx(expected, rel=0.01)


def test_displacement_is_velocity_divided_by_omega():
    """The two orders are consistent with each other, which is the property
    that a second implementation would break."""
    freq = 50.0
    v = float(np.sqrt(np.mean(acceleration_to_velocity_mm_s(
        sine(freq), FS, floor_hz=integration_floor_hz(SHAFT_HZ)) ** 2)))
    d = float(np.sqrt(np.mean(acceleration_to_displacement_um(
        sine(freq), FS, lower_hz=None, upper_hz=None,
        floor_hz=integration_floor_hz(SHAFT_HZ)) ** 2)))
    # v in mm/s -> m/s, divide by omega -> m, to um
    assert (v / 1000.0) / (2.0 * np.pi * freq) * 1e6 == pytest.approx(d, rel=0.01)


# ------------------------------------------- no second integrator --

def test_there_is_only_one_integrator_in_the_codebase():
    """The ticket's second clause, as a test.

    Searches for the integration transfer function -- a division by a power of
    (2*pi*f) applied to a spectrum -- outside casing_orbit.py. A new one is
    never added deliberately; it is added by someone who needs velocity, does
    not find it, and writes four lines that look obviously right.
    """
    app_dir = Path(__file__).resolve().parents[1] / "app"
    allowed = {"casing_orbit.py"}

    # A spectrum multiplied or divided by (2*pi*f) raised to a power.
    pattern = re.compile(
        r"(?:np\.fft\.(?:i?rfft|i?fft))[\s\S]{0,400}?"
        r"(?:2\s*\*\s*(?:np\.pi|math\.pi)|omega)\s*\)?\s*\*\*\s*[12]"
        r"|1\.0\s*/\s*np\.(?:square|power)\(\s*2\.0?\s*\*\s*np\.pi"
    )
    offenders = []
    for path in app_dir.rglob("*.py"):
        if path.name in allowed:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if pattern.search(text):
            offenders.append(str(path.relative_to(app_dir)))

    assert not offenders, (
        "A second integrator appears to have been added in: "
        + ", ".join(offenders)
        + ". Use casing_orbit.acceleration_to_velocity_mm_s or "
        "acceleration_to_displacement_um -- they share one transfer function, "
        "one integration floor and one band mask, and a second copy will drift "
        "from them."
    )
