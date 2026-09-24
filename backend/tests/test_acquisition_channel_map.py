"""The channel map must survive a read-modify-write — found in production.

`PUT /api/v1/acquisition/config` replaced the stored channel map with
whatever the caller sent, and its schema had no sensitivity field at all.
The same model is the GET response shape, so a settings screen reading the
config and saving it back sent entries with no sensitivity and the handler
wrote exactly that.

The result on the live system: a channel map with all eight channels
present, every per-channel mV/g figure gone, and unit resolution quietly
falling back to the sensor-level default. Nothing errored and nothing in
the UI changed. The values the gateway declares on every capture had been
overwritten by a round trip that touched nothing.
"""

from __future__ import annotations

import pytest

from app.schemas.acquisition import ChannelMapEntryIO
from app.routers.acquisition import _merge_channel_map


class StoredConfig:
    def __init__(self, channel_map):
        self.channel_map = channel_map


def stored_with_sensitivities():
    return StoredConfig([
        {"channel_index": i + 1, "machine_axis": "VERTICAL",
         "signal_type": "VIBRATION", "label": None,
         "sensitivity_mv_per_g": 500.0 if i < 2 else 100.0}
        for i in range(8)
    ])


def entries_without_sensitivity():
    """What a client sends back after reading a GET that omitted the field."""
    return [ChannelMapEntryIO(channel_index=i + 1) for i in range(8)]


def test_a_round_trip_that_omits_sensitivity_does_not_erase_it():
    """The exact sequence that lost the data on the live system."""
    merged = _merge_channel_map(stored_with_sensitivities(),
                                entries_without_sensitivity())

    assert [e["sensitivity_mv_per_g"] for e in merged] == \
        [500.0, 500.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0]


def test_the_schema_can_carry_a_sensitivity_at_all():
    """It could not, which is the root of it. The measurement schema for the
    same stored object always could -- two shapes for one thing, one of them
    silently lossy."""
    entry = ChannelMapEntryIO(channel_index=1, sensitivity_mv_per_g=500.0)
    assert entry.sensitivity_mv_per_g == 500.0
    assert "sensitivity_mv_per_g" in entry.model_dump()


def test_the_camel_case_spelling_a_device_reads_back_is_accepted():
    entry = ChannelMapEntryIO.model_validate(
        {"channelIndex": 2, "sensitivityMvPerG": 500.0})
    assert entry.channel_index == 2
    assert entry.sensitivity_mv_per_g == 500.0


def test_a_caller_that_does_send_a_sensitivity_replaces_it():
    """Preserving must not become ignoring."""
    merged = _merge_channel_map(
        stored_with_sensitivities(),
        [ChannelMapEntryIO(channel_index=1, sensitivity_mv_per_g=100.0)])

    assert merged[0]["sensitivity_mv_per_g"] == 100.0
    # and the channels the caller said nothing about are untouched
    assert merged[1]["sensitivity_mv_per_g"] == 500.0


def test_the_fields_the_caller_did_change_are_applied():
    merged = _merge_channel_map(
        stored_with_sensitivities(),
        [ChannelMapEntryIO(channel_index=3, machine_axis="AXIAL",
                           label="Pump DE axial")])

    third = next(e for e in merged if e["channel_index"] == 3)
    assert third["machine_axis"] == "AXIAL"
    assert third["label"] == "Pump DE axial"
    assert third["sensitivity_mv_per_g"] == 100.0, "the sensitivity went with it"


def test_a_label_can_still_be_cleared():
    """`label` is legitimately nullable, so an explicit null must clear it --
    preserving on None would make a label permanent once set."""
    stored = StoredConfig([{"channel_index": 1, "label": "old",
                            "sensitivity_mv_per_g": 500.0}])
    merged = _merge_channel_map(stored, [ChannelMapEntryIO(channel_index=1)])
    assert merged[0]["label"] is None
    assert merged[0]["sensitivity_mv_per_g"] == 500.0


def test_a_new_channel_is_added_rather_than_dropped():
    stored = StoredConfig([{"channel_index": 1, "sensitivity_mv_per_g": 500.0}])
    merged = _merge_channel_map(stored, [ChannelMapEntryIO(channel_index=2)])
    assert [e["channel_index"] for e in merged] == [1, 2]


@pytest.mark.parametrize("existing", [None, StoredConfig(None),
                                      StoredConfig([]), StoredConfig("junk")])
def test_nothing_stored_yet_is_not_an_error(existing):
    merged = _merge_channel_map(existing, entries_without_sensitivity())
    assert len(merged) == 8
    assert all("sensitivity_mv_per_g" not in e or e["sensitivity_mv_per_g"] is None
               for e in merged)


def test_the_merged_map_is_what_unit_resolution_reads():
    """The whole point: these entries feed resolve_channel_unit, and losing
    the sensitivity there makes two 500 mV/g channels read five times high."""
    from app.ai.signal_unit import resolve_channel_unit

    merged = _merge_channel_map(stored_with_sensitivities(),
                                entries_without_sensitivity())
    for zero_based, expected in enumerate([500, 500, 100, 100, 100, 100, 100, 100]):
        unit = resolve_channel_unit(zero_based, channel_map=merged,
                                    sensor_sensitivity=100.0,
                                    device_declared_unit="g")
        assert unit.sensitivity_mv_per_g == expected
        assert unit.sensitivity_source == "channel_map"
