"""Deciding how fast the shaft turns — VIK-036 and VIK-037.

Every order in the platform is a frequency divided by this number. Get it
wrong by two and an outer-race defect at 3.06 orders reads as 1.53, which
names nothing; get it wrong by four and unbalance at 1.00 reads as 0.25.

The estimator this replaces returned 2x or 4x the true speed on all eight
channels of the test pump. These tests are built around that measurement,
because the failure is not a tuning problem: the tallest line in a spectrum
is frequently not the shaft, and nothing in the spectrum alone can say which
of two real peaks is 1x.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.ai.shaft_speed import (
    CANDIDATE_MULTIPLES,
    NAMEPLATE_TOLERANCE,
    ShaftSpeed,
    resolve_shaft_speed,
)

FS = 50_000.0
N = 13_888
LINE_HZ = FS / N                      # 3.60 Hz, as the real captures have
TRUE_HZ = 1480 / 60.0                 # 24.667 Hz


def spectrum_with(peaks: dict[float, float]):
    """A spectrum with lines at the given frequencies and amplitudes."""
    freqs = np.fft.rfftfreq(N, d=1.0 / FS)
    amps = np.full(freqs.size, 0.001)
    for hz, amplitude in peaks.items():
        amps[int(np.argmin(np.abs(freqs - hz)))] = amplitude
    return freqs, amps


#: What the test pump's channels actually look like: the biggest line is 4x,
#: sharing its bin with twice mains, and 1x is present but smaller.
PUMP = {TRUE_HZ: 0.004, 2 * TRUE_HZ: 0.010, 4 * TRUE_HZ: 0.030}


# --------------------------------------------- the failure being prevented --

def test_the_tallest_line_is_not_the_shaft_and_the_nameplate_says_so():
    """The measurement this module exists for. On all eight channels the
    largest line was 2x or 4x the true speed; taking it put every order out
    by that factor."""
    freqs, amps = spectrum_with(PUMP)
    result = resolve_shaft_speed(freqs, amps, nameplate_rpm=1480)

    assert result.hz == pytest.approx(TRUE_HZ, abs=0.01)
    assert result.spectrum_hz == pytest.approx(4 * TRUE_HZ, abs=LINE_HZ)
    assert result.source == "nameplate_confirmed"
    assert result.usable


def test_it_says_which_multiple_the_peak_turned_out_to_be():
    """The reader has to be able to see why the loudest thing on screen was
    not used, or the number looks arbitrary."""
    freqs, amps = spectrum_with(PUMP)
    note = resolve_shaft_speed(freqs, amps, nameplate_rpm=1480).note
    assert "4x the nameplate speed, not 1x" in note
    assert "out by 4 times" in note


def test_a_peak_that_is_the_shaft_is_recognised_as_agreement():
    freqs, amps = spectrum_with({TRUE_HZ: 0.03, 2 * TRUE_HZ: 0.004})
    result = resolve_shaft_speed(freqs, amps, nameplate_rpm=1480)

    assert result.source == "nameplate_confirmed"
    assert result.confidence == pytest.approx(0.95)
    assert "agree to within" in result.note


# ------------------------------------------------------ order of authority --

def test_a_tacho_beats_everything():
    """A measured speed is first-hand and current. A nameplate is neither."""
    freqs, amps = spectrum_with(PUMP)
    result = resolve_shaft_speed(freqs, amps, measured_rpm=1476, nameplate_rpm=1480)

    assert result.hz == pytest.approx(1476 / 60.0)
    assert result.source == "measured"
    assert result.confidence == 1.0


def test_the_nameplate_beats_the_spectrum():
    freqs, amps = spectrum_with(PUMP)
    assert resolve_shaft_speed(freqs, amps, nameplate_rpm=1480).hz \
        == pytest.approx(TRUE_HZ, abs=0.01)


def test_an_operating_range_beats_the_unconstrained_peak():
    """Even without a nameplate, knowing the machine runs at 1440-1500 rpm
    rules out a 98 Hz answer outright."""
    freqs, amps = spectrum_with(PUMP)
    result = resolve_shaft_speed(freqs, amps,
                                 operating_rpm_min=1440, operating_rpm_max=1500)

    assert result.hz == pytest.approx(TRUE_HZ, rel=0.02)
    assert result.source in ("spectrum_in_range", "operating_range")
    assert result.usable


def test_a_range_narrower_than_the_line_spacing_still_answers():
    """1440-1500 rpm is a 1.0 Hz window and the lines are 3.6 Hz apart, so
    frequently no line falls inside it. Falling through to the unconstrained
    peak there would throw away real machine knowledge in favour of the guess
    that reads 4x."""
    freqs, amps = spectrum_with({4 * TRUE_HZ: 0.03})      # nothing near 1x
    result = resolve_shaft_speed(freqs, amps,
                                 operating_rpm_min=1440, operating_rpm_max=1500)

    assert result.source == "operating_range"
    assert result.hz == pytest.approx((1440 + 1500) / 2 / 60.0)
    assert result.usable
    assert "cannot resolve inside it" in result.note


# ------------------------------------------------- refusing to be trusted --

def test_a_bare_peak_is_returned_but_marked_unusable():
    """Something is still better than nothing for a plot axis. But no engine
    may compute an order from it, so confidence sits below the bar."""
    freqs, amps = spectrum_with(PUMP)
    result = resolve_shaft_speed(freqs, amps)

    assert result.hz == pytest.approx(4 * TRUE_HZ, abs=LINE_HZ)
    assert result.source == "spectrum_unconstrained"
    assert not result.usable
    assert "not trustworthy" in result.note


def test_nothing_at_all_is_an_honest_unknown():
    result = resolve_shaft_speed()
    assert result.hz is None
    assert result.source == "none"
    assert not result.usable
    assert "unknown" in result.note


def test_usable_is_the_single_gate():
    assert ShaftSpeed(hz=24.6, confidence=0.95).usable
    assert not ShaftSpeed(hz=24.6, confidence=0.3).usable
    assert not ShaftSpeed(hz=None, confidence=1.0).usable
    assert not ShaftSpeed(hz=0.0, confidence=1.0).usable


def test_a_spectrum_that_matches_no_multiple_lowers_confidence():
    """A machine running nowhere near its nameplate is either loaded oddly or
    this channel is dominated by something that is not the shaft. Either way
    the nameplate is still the best answer, but a less certain one."""
    freqs, amps = spectrum_with({37.3: 0.03})     # 1.51x -- between orders
    result = resolve_shaft_speed(freqs, amps, nameplate_rpm=1480)

    assert result.source == "nameplate"
    assert result.confidence == pytest.approx(0.6)
    assert "not within" in result.note


# ------------------------------------------------------------- slip, etc --

def test_normal_induction_slip_still_counts_as_agreement():
    """A 1500 rpm synchronous machine runs 1440-1490 loaded. That is up to 4%
    low and must not read as disagreement."""
    for rpm in (1440, 1460, 1480, 1490):
        freqs, amps = spectrum_with({rpm / 60.0: 0.03})
        result = resolve_shaft_speed(freqs, amps, nameplate_rpm=1480)
        assert result.source == "nameplate_confirmed", rpm


def test_the_tolerance_does_not_reach_the_next_order():
    """If it did, a 2x peak would be accepted as 1x and the module would do
    the opposite of its job."""
    assert NAMEPLATE_TOLERANCE < 0.5
    assert 0.5 in CANDIDATE_MULTIPLES, "looseness puts a real line at half order"


def test_half_order_is_recognised_rather_than_read_as_the_shaft():
    """Looseness produces a 0.5x line. On a badly loose machine it can be the
    largest one, and reading it as 1x halves every order in the report."""
    freqs, amps = spectrum_with({TRUE_HZ / 2: 0.03, TRUE_HZ: 0.01})
    result = resolve_shaft_speed(freqs, amps, nameplate_rpm=1480)

    assert result.hz == pytest.approx(TRUE_HZ, abs=0.01)
    assert result.source == "nameplate_confirmed"
    assert "0.5x the nameplate speed" in result.note


def test_rpm_reads_back_as_rpm():
    assert resolve_shaft_speed(measured_rpm=1480).rpm == pytest.approx(1480)
    assert ShaftSpeed().rpm is None


@pytest.mark.parametrize("bad", [0, -1, None])
def test_a_nonsense_speed_is_not_taken(bad):
    freqs, amps = spectrum_with(PUMP)
    result = resolve_shaft_speed(freqs, amps, measured_rpm=bad, nameplate_rpm=bad)
    assert result.source != "measured"
    assert result.source != "nameplate"
