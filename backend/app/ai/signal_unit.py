"""What the stored numbers physically are — VIK-005.

The platform writes `scaled_eng` as the unit of every feature, which says
nothing: it means "whatever scale the file arrived in". Readings are stored
exactly as the device sent them, and volts and g differ by a factor of ten.
Read one way the test pump measures 34 mm/s, read the other 344. The level at
which a machine is damaging itself is around 7 to 11.

So this module answers one question — what unit is a channel in — and refuses
to answer when it does not know.

**Refusing is the feature.** The ticket is explicit: do not guess when
sensitivity is absent, write `unconfirmed` and let downstream engines refuse.
A guessed unit does not produce an obviously wrong number, it produces a
plausible one, and a plausible wrong severity gets acted on.

**Sensitivity is per channel.** Not per sensor, because in practice it is not
uniform: on the gateway measured here ch1 and ch2 are 500 mV/g while ch3-ch8
are 100, and the cloud configuration reports a single 100 for all eight.
Dividing every channel by one figure leaves two of them wrong by five times,
looking entirely ordinary. The per-channel value lives on the existing
channel_map entry; the sensor-level value is the fallback.

**Conversion is not applied twice.** Where the device already converted -- the
Beckhoff gateway applies counts x (5 V / 32768) / sensitivity before
publishing, so its CSVs are already in g -- dividing again would be wrong by
the sensitivity a second time. `declared_unit` on the upload is what says so.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

#: What the platform writes today. Means "unknown scale", not a unit.
UNKNOWN_UNIT = "scaled_eng"

#: What a channel reads when nobody has established its unit. Downstream
#: engines are expected to refuse on this rather than assume.
UNCONFIRMED = "unconfirmed"

#: Units a channel can be in once it IS known.
ACCELERATION_G = "g"
VOLTS = "V"
VELOCITY_MM_S = "mm/s"

KNOWN_UNITS = (ACCELERATION_G, VOLTS, VELOCITY_MM_S)


@dataclass
class ChannelUnit:
    """The unit of one channel, and how confident we are in it."""
    channel_index: int
    unit: str = UNCONFIRMED
    #: mV/g actually used, when a conversion was applied.
    sensitivity_mv_per_g: Optional[float] = None
    #: "channel_map" | "sensor" | "device" | "none" -- where the figure came
    #: from, so a wrong number can be traced to the record that caused it.
    sensitivity_source: str = "none"
    confirmed: bool = False
    #: Set when the unit could not be established. This is not an error state;
    #: it is the honest answer, and it is what downstream engines read.
    reason: Optional[str] = None

    @property
    def usable(self) -> bool:
        """True when a severity may be computed from this channel."""
        return self.confirmed and self.unit in KNOWN_UNITS


def sensitivity_for_channel(
    channel_index: int,
    channel_map: Optional[list[dict[str, Any]]],
    sensor_sensitivity: Optional[float],
) -> tuple[Optional[float], str]:
    """The mV/g to use for one channel, and where it came from.

    Channel first, sensor second. The sensor-level figure is a fallback rather
    than a default: it is right for the channels it describes and wrong for
    any that differ, and only the channel map can say which is which.

    channel_map is 1-based (CH1 = 1); channel_index here is 0-based, matching
    the sample arrays. Getting that wrong shifts every sensitivity by one
    channel, which is why the conversion happens in one place.
    """
    for entry in channel_map or []:
        if int(entry.get("channel_index", -1)) == channel_index + 1:
            value = entry.get("sensitivity_mv_per_g")
            if value:
                return float(value), "channel_map"
            break

    if sensor_sensitivity:
        return float(sensor_sensitivity), "sensor"
    return None, "none"


def resolve_channel_unit(
    channel_index: int,
    *,
    channel_map: Optional[list[dict[str, Any]]] = None,
    sensor_sensitivity: Optional[float] = None,
    sensor_signal_unit: Optional[str] = None,
    sensor_unit_confirmed: bool = False,
    device_declared_unit: Optional[str] = None,
) -> ChannelUnit:
    """Decide what one channel's samples are in.

    Order of authority:

    1. What the DEVICE says it sent. The gateway converts to g before
       publishing, so its word is first-hand and nothing further is applied.
    2. What the SENSOR record says, but only when someone confirmed it.
    3. Otherwise unconfirmed, with the reason.

    A sensitivity on its own does not establish a unit. Knowing a transducer
    is 100 mV/g tells you how to convert volts to g; it does not tell you
    whether what arrived was volts.
    """
    result = ChannelUnit(channel_index=channel_index)
    sensitivity, source = sensitivity_for_channel(
        channel_index, channel_map, sensor_sensitivity
    )
    result.sensitivity_mv_per_g = sensitivity
    result.sensitivity_source = source

    if device_declared_unit and device_declared_unit in KNOWN_UNITS:
        # First-hand and already applied. Converting again would divide by the
        # sensitivity twice.
        result.unit = device_declared_unit
        result.confirmed = True
        return result

    if sensor_unit_confirmed and sensor_signal_unit in KNOWN_UNITS:
        result.unit = sensor_signal_unit
        result.confirmed = True
        return result

    result.unit = UNCONFIRMED
    result.confirmed = False
    if sensitivity is None:
        result.reason = (
            f"No sensitivity is declared for channel {channel_index} on this "
            f"sensor or in its channel map, and the device did not say what it "
            f"sent. The stored numbers could be volts or g, which differ by a "
            f"factor of ten."
        )
    else:
        result.reason = (
            f"Sensitivity is known ({sensitivity:g} mV/g from the "
            f"{source.replace('_', ' ')}), but nobody has confirmed what unit "
            f"the stored samples are already in, so applying it could convert "
            f"a value that was converted once already."
        )
    return result


def to_acceleration_g(samples: list[float], unit: ChannelUnit) -> Optional[list[float]]:
    """Convert one channel's samples to g, or return None if that cannot be done.

    None rather than an exception, and never the samples unchanged: handing
    back the input on failure is how an unconverted reading ends up being
    graded as though it were converted.
    """
    if not unit.usable:
        return None
    if unit.unit == ACCELERATION_G:
        return list(samples)
    if unit.unit == VOLTS:
        if not unit.sensitivity_mv_per_g:
            return None
        # mV/g -> V/g, then V / (V/g) = g
        volts_per_g = unit.sensitivity_mv_per_g / 1000.0
        return [s / volts_per_g for s in samples]
    # mm/s is a velocity; converting it to g needs a frequency and belongs in
    # units.py, not here.
    return None


def describe(units: list[ChannelUnit]) -> dict[str, Any]:
    """A summary for the API and for anything that has to explain itself."""
    usable = [u for u in units if u.usable]
    return {
        "channels": len(units),
        "usable": len(usable),
        "all_confirmed": len(usable) == len(units) and bool(units),
        "units": sorted({u.unit for u in units}),
        "sensitivity_sources": sorted({u.sensitivity_source for u in units}),
        "blocked_reasons": sorted({u.reason for u in units if u.reason}),
    }
