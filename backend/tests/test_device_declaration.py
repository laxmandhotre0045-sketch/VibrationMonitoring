"""Recording what the device says its samples are — the wire for VIK-005.

VIK-005's refusal rule and VIK-006's columns both worked from the day they
were written. What did not exist was anything that ever set them, so the
refusal fired on all 94 stored captures — correctly, on information the
platform was never given.

These tests are mostly about the ways a declaration can be wrong, because a
declaration is the one input that changes what every severity downstream
means. A sensitivity attached to the wrong channel is wrong by the ratio
between the two — five times on this gateway — and looks entirely ordinary.
"""

from __future__ import annotations

import pytest

from app.ai.signal_unit import (
    ACCELERATION_G,
    UNCONFIRMED,
    VOLTS,
    resolve_channel_unit,
)
from app.services.device_declaration import (
    MAX_SENSITIVITY_MV_PER_G,
    parse_sensitivities,
    record_declaration,
)


class FakeSensor:
    def __init__(self, signal_unit=UNCONFIRMED, unit_confirmed=False, sensitivity=100.0):
        self.signal_unit = signal_unit
        self.unit_confirmed = unit_confirmed
        self.sensitivity = sensitivity


class FakePlotConfig:
    def __init__(self, channel_map=None):
        self.channel_map = channel_map if channel_map is not None else []


class FakeSession:
    """Records what was handed to add(); nothing here touches a database."""
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)


GATEWAY = "500,500,100,100,100,100,100,100"


def declare(unit="g", sensitivities=GATEWAY, channels=8,
            sensor=None, plot_config=None):
    db = FakeSession()
    sensor = sensor if sensor is not None else FakeSensor()
    plot_config = plot_config if plot_config is not None else FakePlotConfig()
    result = record_declaration(
        db, sensor=sensor, plot_config=plot_config,
        sample_unit=unit, sensitivity_csv=sensitivities, channel_count=channels,
    )
    return result, sensor, plot_config


# ------------------------------------------------------ the happy path --

def test_the_gateways_own_declaration_confirms_the_sensor():
    """The whole point. gateway/.env says SAMPLE_UNIT=g and lists eight
    sensitivities; after one capture the sensor is gradeable."""
    result, sensor, config = declare()

    assert result.unit == ACCELERATION_G
    assert sensor.signal_unit == ACCELERATION_G
    assert sensor.unit_confirmed is True
    assert result.channels_updated == 8
    assert [e["sensitivity_mv_per_g"] for e in config.channel_map] == \
        [500, 500, 100, 100, 100, 100, 100, 100]


def test_the_two_loud_channels_keep_their_own_figure():
    """ch1 and ch2 are 500 mV/g and the rest are 100. The cloud configuration
    reports a single 100 for all eight, which is wrong for those two by five
    times — and five times is the difference between ordinary and alarming."""
    _, sensor, config = declare()

    for zero_based, expected in enumerate([500, 500, 100, 100, 100, 100, 100, 100]):
        unit = resolve_channel_unit(
            zero_based,
            channel_map=config.channel_map,
            sensor_sensitivity=sensor.sensitivity,
            device_declared_unit="g",
        )
        assert unit.sensitivity_mv_per_g == expected, f"channel {zero_based}"
        assert unit.sensitivity_source == "channel_map"


def test_the_channel_map_is_written_one_based():
    """ChannelMapEntry and sensitivity_for_channel both treat CH1 as 1. Written
    zero-based, every sensitivity lands on its neighbour."""
    _, _, config = declare()
    assert [e["channel_index"] for e in config.channel_map] == [1, 2, 3, 4, 5, 6, 7, 8]


def test_an_existing_channel_map_keeps_its_wiring():
    """The map already describes axis, signal type and label. Adding a
    sensitivity must not discard them."""
    existing = [{"channel_index": 1, "machine_axis": "AXIAL",
                 "signal_type": "VIBRATION", "label": "Pump DE axial"}]
    _, _, config = declare(plot_config=FakePlotConfig(existing))

    first = config.channel_map[0]
    assert first["machine_axis"] == "AXIAL"
    assert first["label"] == "Pump DE axial"
    assert first["sensitivity_mv_per_g"] == 500


def test_the_config_is_reassigned_so_the_write_is_not_lost():
    """SQLAlchemy does not notice a list mutated in place on a JSON column, so
    the whole map has to be reassigned or the update silently vanishes."""
    config = FakePlotConfig()
    before = config.channel_map
    result, _, config = declare(plot_config=config)
    assert config.channel_map is not before
    assert result.channels_updated == 8


# ----------------------------------------------- refusing a bad declaration --

def test_an_unrecognised_unit_leaves_the_sensor_alone():
    """'counts' is what the PLC deals in. Recording it as a unit would confirm
    a sensor whose numbers nobody can interpret; the safe state is the one it
    is already in."""
    result, sensor, _ = declare(unit="counts")

    assert result.unit is None
    assert sensor.signal_unit == UNCONFIRMED
    assert sensor.unit_confirmed is False
    assert any("not a unit this platform recognises" in w for w in result.warnings)


def test_no_declaration_at_all_changes_nothing():
    """An older gateway that has not been updated must not be treated as
    having said anything."""
    result, sensor, _ = declare(unit=None, sensitivities=None)

    assert result.unit is None
    assert sensor.signal_unit == UNCONFIRMED
    assert sensor.unit_confirmed is False
    assert result.warnings == []


@pytest.mark.parametrize("bad,reason", [
    ("500,500,100", "too few"),
    ("500,500,100,100,100,100,100,100,100", "too many"),
    ("500,abc,100,100,100,100,100,100", "not a number"),
    ("500,-100,100,100,100,100,100,100", "negative"),
    ("500,0,100,100,100,100,100,100", "zero"),
])
def test_a_bad_sensitivity_list_is_ignored_whole_not_in_part(bad, reason):
    """Partly applying a list is the dangerous outcome: the good values land
    and the reader has no way to see which channels were skipped."""
    result, _, config = declare(sensitivities=bad)

    assert result.sensitivities == [], reason
    assert config.channel_map == []
    assert result.warnings


def test_a_list_for_the_wrong_channel_count_is_not_padded():
    """Eight figures against four channels is a configuration mismatch, and
    truncating it puts ch1's 500 on a channel that may be a 100."""
    result, _, _ = declare(sensitivities=GATEWAY, channels=4)
    assert result.sensitivities == []
    assert any("8 sensitivities were declared for 4 channels" in w
               for w in result.warnings)


def test_an_implausible_sensitivity_is_refused():
    huge = ",".join([str(MAX_SENSITIVITY_MV_PER_G + 1)] * 8)
    result, _, _ = declare(sensitivities=huge)
    assert result.sensitivities == []
    assert any("outside the plausible range" in w for w in result.warnings)


def test_parse_sensitivities_reports_rather_than_raises():
    warnings: list[str] = []
    assert parse_sensitivities("not,a,list", 3, warnings) == []
    assert warnings
    assert parse_sensitivities(None, 8, []) == []
    assert parse_sensitivities("", 8, []) == []


# ------------------------------------------- a unit that changes under us --

def test_a_changed_unit_is_recorded_and_loudly_flagged():
    """A sensor does not change unit by itself. Either it was rewired or
    something is misconfigured, and both need a person — but every feature
    stored before this capture was read the old way, which is the part that
    matters and the part a bare value would not say."""
    sensor = FakeSensor(signal_unit=ACCELERATION_G, unit_confirmed=True)
    result, sensor, _ = declare(unit="V", sensor=sensor)

    assert result.unit == VOLTS
    assert sensor.signal_unit == VOLTS
    assert result.unit_changed is True
    warning = " ".join(result.warnings)
    assert "was recorded as 'g'" in warning
    assert "now declares 'V'" in warning
    assert "before this capture was read as 'g'" in warning


def test_the_same_unit_declared_again_is_not_flagged_as_a_change():
    """Every capture carries the declaration, so a warning on each one would
    be noise and would train people to ignore the real one."""
    sensor = FakeSensor(signal_unit=ACCELERATION_G, unit_confirmed=True)
    result, _, _ = declare(unit="g", sensor=sensor)

    assert result.unit_changed is False
    assert not any("now declares" in w for w in result.warnings)


def test_moving_off_unconfirmed_is_not_a_change_of_unit():
    """'unconfirmed' is the absence of an answer, not a previous answer."""
    result, _, _ = declare(unit="g", sensor=FakeSensor(signal_unit=UNCONFIRMED))
    assert result.unit_changed is False


# ----------------------------------------------------- what it tells you --

def test_non_uniform_sensitivities_are_pointed_out():
    """The sensor record carries one figure and the channels do not agree with
    it. That is not an error, but the reader should know which won."""
    result, _, _ = declare()
    assert any("not uniform" in w and "100 mV/g" in w for w in result.warnings)


def test_uniform_sensitivities_say_nothing():
    result, _, _ = declare(sensitivities="100,100,100,100,100,100,100,100")
    assert not any("not uniform" in w for w in result.warnings)


def test_sensitivities_with_nowhere_to_go_are_reported():
    db = FakeSession()
    sensor = FakeSensor()
    result = record_declaration(db, sensor=sensor, plot_config=None,
                                sample_unit="g", sensitivity_csv=GATEWAY,
                                channel_count=8)
    assert result.unit == ACCELERATION_G
    assert any("no plot configuration" in w for w in result.warnings)


def test_a_declaration_never_raises_whatever_arrives():
    """A capture is worth keeping even when nobody can yet say what it is.
    Losing it to a malformed header would be the worst outcome of all."""
    for unit in (None, "", "g", "counts", "  ", "\x00", "g" * 500):
        for sens in (None, "", "junk", ",,,,", GATEWAY, "1e400,2,3,4,5,6,7,8"):
            record_declaration(FakeSession(), sensor=FakeSensor(),
                               plot_config=FakePlotConfig(),
                               sample_unit=unit, sensitivity_csv=sens,
                               channel_count=8)
