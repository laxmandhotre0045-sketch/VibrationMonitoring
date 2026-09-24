"""Payload parsing on the gateway — the helpers where a wrong answer is silent.

Everything else in my_script.py talks to a broker or a filesystem. These two
functions are pure, they run on every message the PLC sends, and until now
nothing tested them.

That mattered. At 15:59:05 the gateway logged five of these:

    [ERROR] Failed to handle MQTT message: [Errno 22] Invalid argument

and threw away five complete windows of samples. The cause was
`to_epoch_ms` raising `OSError` on a timestamp from before 1970 -- a PLC that
has not yet set its clock -- while the handler around it caught only
`ValueError`. The exception escaped the function, escaped `parse_message`,
and reached `on_message`, which drops the whole message.

The samples in those messages were fine. Only the clock was wrong.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from my_script import parse_message, to_epoch_ms  # noqa: E402


# ------------------------------------------- the bug that lost real data --

@pytest.mark.parametrize("stamp", [
    "1601-01-01T00:00:00",   # Windows epoch: an unset FILETIME clock
    "1900-01-01T00:00:00",
    "1969-12-31T23:59:59",   # one second before the Unix epoch
    "0001-01-01T00:00:00",   # datetime.min, what a zeroed struct decodes to
    "9999-12-31T23:59:59",   # datetime.max, the same mistake upward
])
def test_a_clock_outside_the_unix_epoch_does_not_raise(stamp):
    """On Windows, astimezone() and timestamp() go through the platform's
    localtime, which rejects these with OSError rather than ValueError. The
    handler caught only ValueError, so the message died."""
    assert to_epoch_ms(stamp) is None


def test_a_message_with_an_unset_clock_keeps_its_samples():
    """The consequence, end to end. An unknown timestamp is something the
    caller already handles -- it falls back to the arrival time -- but only
    if the parse returns rather than raising."""
    payload = json.dumps({
        "System Timestamp": "1601-01-01T00:00:00",
        "Ch1": [1.0, 2.0, 3.0],
        "Ch2": [4.0, 5.0, 6.0],
    }).encode()

    timestamp, rows = parse_message(payload, 8)

    assert timestamp is None, "an unusable clock must read as unknown"
    assert len(rows) == 3, "the samples were thrown away with the timestamp"
    assert rows[0][:2] == [1.0, 4.0]


# ----------------------------------------------- timestamps that do work --

def test_the_shapes_the_plc_actually_sends():
    assert to_epoch_ms("2026-09-21T15:59:05.123") == 1789986545123
    assert to_epoch_ms(1789986545123) == 1789986545123          # milliseconds
    assert to_epoch_ms(1789986545) == 1789986545000             # seconds
    assert to_epoch_ms("1789986545123") == 1789986545123        # as a string


def test_the_colon_before_milliseconds_quirk():
    """One device writes 16:52:11:210 instead of 16:52:11.210."""
    assert to_epoch_ms("2026-09-21T15:59:05:123") == \
        to_epoch_ms("2026-09-21T15:59:05.123")


def test_a_windows_filetime_is_recognised():
    """100-nanosecond ticks since 1601, which is what a Beckhoff clock reads."""
    filetime = (1789986545123 + 11644473600000) * 10000
    assert to_epoch_ms(filetime) == pytest.approx(1789986545123, abs=1)


@pytest.mark.parametrize("junk", [
    None, "", "   ", "garbage", "not-a-date", 0, -1, 12345, [1, 2], {"a": 1},
])
def test_nothing_unusable_raises_or_is_invented(junk):
    """Every one of these means "no usable timestamp", and the caller turns
    that into the arrival time. What none of them may do is raise."""
    assert to_epoch_ms(junk) is None


def test_a_time_no_machine_could_have_run_at_is_refused():
    """1e20 was converted rather than rejected, landing in the year 318,857.
    A timestamp that absurd is not a late clock, it is a misread field, and
    carrying it through sets the capture's whole time axis wrong."""
    assert to_epoch_ms(1e20) is None
    assert to_epoch_ms("3000-01-01T00:00:00") is None


# ------------------------------------------------------- message shapes --

def test_channels_are_read_in_order_whatever_they_are_called():
    for key in ("Ch{}", "CH{}", "channel{}", "Channel_{}", "Sensor{}"):
        payload = json.dumps({
            "timestamp_ms": 1789986545123,
            key.format(1): [1.0], key.format(2): [2.0], key.format(3): [3.0],
        }).encode()
        _, rows = parse_message(payload, 8)
        assert rows and rows[0][:3] == [1.0, 2.0, 3.0], key


def test_an_unparseable_payload_returns_nothing_rather_than_raising():
    """`add_message` checks `if not rows`, so None and [] are equally fine.
    What must not happen is an exception, which drops the message."""
    for payload in (b"", b"not json", b"{}", b"[]", b'{"Ch1": "text"}',
                    bytes([0, 1, 2]), b'{"Ch1": [1, 2}'):
        timestamp, rows = parse_message(payload, 8)
        assert not rows
