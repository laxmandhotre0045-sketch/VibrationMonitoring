"""Tests for unit resolution — VIK-005.

The ticket's acceptance is two clauses: "features carry a real unit; an
undeclared capture is flagged, never assumed". The second clause is the one
worth most tests, because guessing does not produce an obviously wrong number.
It produces a plausible one, and a plausible wrong severity gets acted on.

The roadmap puts it plainly: read one way the test pump measures 34 mm/s, read
the other 344, and the damaging level is around 7 to 11.
"""

from __future__ import annotations

import pytest

from app.ai.signal_unit import (
    ACCELERATION_G,
    UNCONFIRMED,
    VOLTS,
    ChannelUnit,
    describe,
    resolve_channel_unit,
    sensitivity_for_channel,
    to_acceleration_g,
)

EIGHT = [{"channel_index": i + 1} for i in range(8)]
MIXED = [
    {"channel_index": i + 1, "sensitivity_mv_per_g": 500.0 if i < 2 else 100.0}
    for i in range(8)
]


# ------------------------------------------------------ refusing to guess --

def test_an_undeclared_capture_is_unconfirmed_not_assumed_g():
    """The state of this deployment today: a sensitivity is on record, but
    nobody has said what the stored samples already are."""
    u = resolve_channel_unit(0, channel_map=EIGHT, sensor_sensitivity=100.0)
    assert u.unit == UNCONFIRMED
    assert u.confirmed is False
    assert u.usable is False
    assert u.reason


def test_no_sensitivity_anywhere_is_also_refused_and_says_why():
    u = resolve_channel_unit(0, channel_map=None, sensor_sensitivity=None)
    assert u.usable is False
    assert "factor of ten" in u.reason


def test_conversion_refuses_rather_than_returning_the_input():
    """Handing back unconverted samples on failure is how a raw reading ends
    up graded as though it had been converted. None forces the caller to
    notice."""
    u = resolve_channel_unit(0, channel_map=EIGHT, sensor_sensitivity=100.0)
    assert to_acceleration_g([1.0, 2.0, 3.0], u) is None


def test_a_sensitivity_alone_does_not_establish_a_unit():
    """Knowing a transducer is 100 mV/g tells you how to convert volts to g.
    It does not tell you whether what arrived was volts."""
    u = resolve_channel_unit(0, channel_map=MIXED, sensor_sensitivity=100.0)
    assert u.sensitivity_mv_per_g == 500.0     # known
    assert u.usable is False                    # still not usable


# -------------------------------------------------------- per channel --

def test_a_channel_uses_its_own_sensitivity_before_the_sensors():
    value, source = sensitivity_for_channel(0, MIXED, sensor_sensitivity=100.0)
    assert (value, source) == (500.0, "channel_map")


def test_a_channel_without_its_own_falls_back_to_the_sensor():
    value, source = sensitivity_for_channel(0, EIGHT, sensor_sensitivity=100.0)
    assert (value, source) == (100.0, "sensor")


def test_the_two_loud_channels_are_not_given_the_quiet_figure():
    """The actual hardware: ch1 and ch2 are 500 mV/g, ch3-ch8 are 100, and the
    cloud config reports a single 100 for all eight. Using one figure leaves
    two channels wrong by five times, looking entirely ordinary."""
    per_channel = [
        sensitivity_for_channel(i, MIXED, sensor_sensitivity=100.0)[0]
        for i in range(8)
    ]
    assert per_channel[:2] == [500.0, 500.0]
    assert per_channel[2:] == [100.0] * 6


def test_the_channel_map_is_one_based_and_samples_are_zero_based():
    """Off by one here shifts every sensitivity onto the wrong channel, which
    is silent and wrong everywhere downstream."""
    single = [{"channel_index": 3, "sensitivity_mv_per_g": 777.0}]
    assert sensitivity_for_channel(2, single, None)[0] == 777.0   # CH3 -> index 2
    assert sensitivity_for_channel(3, single, None)[0] is None


# ------------------------------------------------------- when it is known --

def test_a_device_that_declares_its_unit_is_believed():
    """The gateway applies counts x (5 V / 32768) / sensitivity before
    publishing, so its CSVs are already in g and its word is first-hand."""
    u = resolve_channel_unit(0, channel_map=MIXED, sensor_sensitivity=100.0,
                             device_declared_unit="g")
    assert u.unit == ACCELERATION_G
    assert u.usable is True


def test_samples_already_in_g_are_not_divided_again():
    """Dividing a converted value by the sensitivity a second time is wrong by
    exactly the sensitivity, and the result still looks like a reading."""
    u = resolve_channel_unit(0, channel_map=MIXED, device_declared_unit="g")
    assert to_acceleration_g([1.0, 2.0], u) == [1.0, 2.0]


def test_volts_are_converted_using_the_channels_own_sensitivity():
    u = resolve_channel_unit(0, channel_map=MIXED, sensor_signal_unit=VOLTS,
                             sensor_unit_confirmed=True)
    # 0.5 V at 500 mV/g -> 1 g
    assert to_acceleration_g([0.5], u) == pytest.approx([1.0])


def test_volts_without_a_sensitivity_cannot_be_converted():
    u = ChannelUnit(channel_index=0, unit=VOLTS, confirmed=True,
                    sensitivity_mv_per_g=None)
    assert to_acceleration_g([0.5], u) is None


def test_a_confirmed_sensor_unit_is_used_when_the_device_says_nothing():
    u = resolve_channel_unit(0, channel_map=MIXED, sensor_signal_unit="g",
                             sensor_unit_confirmed=True)
    assert u.usable is True


def test_an_unconfirmed_sensor_unit_is_not_used_even_if_it_says_g():
    """unit_confirmed exists precisely so a default cannot masquerade as a
    measurement."""
    u = resolve_channel_unit(0, channel_map=MIXED, sensor_signal_unit="g",
                             sensor_unit_confirmed=False)
    assert u.usable is False


# ---------------------------------------------------------- the summary --

def test_the_summary_reports_nothing_usable_when_nothing_is_confirmed():
    units = [resolve_channel_unit(i, channel_map=EIGHT, sensor_sensitivity=100.0)
             for i in range(8)]
    summary = describe(units)
    assert summary["usable"] == 0
    assert summary["all_confirmed"] is False
    assert summary["blocked_reasons"]


def test_the_summary_reports_all_confirmed_once_the_device_declares():
    units = [resolve_channel_unit(i, channel_map=MIXED, device_declared_unit="g")
             for i in range(8)]
    summary = describe(units)
    assert summary["usable"] == 8
    assert summary["all_confirmed"] is True
    assert summary["units"] == ["g"]
