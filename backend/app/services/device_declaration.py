"""Record what the device said its samples are — the missing half of VIK-005.

VIK-005 built the rule that a capture with no declared unit is refused rather
than graded, and VIK-006 added the columns to hold the answer. Both work. What
was missing is the wire between them and the gateway.

The gateway has known all along. `gateway/.env` carries::

    SAMPLE_UNIT=g
    SENSITIVITY_MV_PER_G=500,500,100,100,100,100,100,100

and `my_script.py` attaches both to every upload -- but only on the leg going
to Senvia. `platform_push.py`, the leg that feeds this platform, sent only
device id, rate, channel count and time, and `/api/v1/ingest/raw` had no field
to receive them anyway. So `sensor_configurations.signal_unit` stayed
'unconfirmed', and VIK-005's refusal fired on every capture ever ingested --
correctly, on information it should have had.

This module is what closes it. Two rules govern everything here:

**A declaration is evidence, not an instruction.** The device is the most
direct witness to what it sent -- `resolve_channel_unit` ranks it above the
sensor record for exactly that reason -- but a misconfigured gateway is still
possible, so every write says where the value came from and an unrecognised
unit is refused outright rather than stored. Refusing keeps the system in the
state it is already in, which is the safe one.

**A change of declaration is reported, never applied silently.** If a sensor
has been saying 'g' for a thousand captures and one arrives saying 'V', that
is either a rewiring or a mistake, and both need a human. The new value is
recorded, because it is what the device actually sent, and the change is
returned as a warning that reaches the ingest acknowledgement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.ai.signal_unit import UNCONFIRMED, normalise_unit

#: Largest sensitivity worth believing, in mV/g. Matches the bound already on
#: ChannelMapEntry so the two cannot disagree about what is plausible.
MAX_SENSITIVITY_MV_PER_G = 100_000.0


@dataclass
class DeclarationResult:
    """What was recorded, and anything the operator should know about it."""
    unit: Optional[str] = None
    unit_changed: bool = False
    sensitivities: list[Optional[float]] = field(default_factory=list)
    channels_updated: int = 0
    warnings: list[str] = field(default_factory=list)


def parse_sensitivities(raw: Optional[str], channel_count: int,
                        warnings: list[str]) -> list[Optional[float]]:
    """A comma-separated list of mV/g, one per channel, or nothing.

    Length must match the channel count exactly. A short list is not padded
    and a long one is not truncated: either would silently attach a figure to
    the wrong channel, and a sensitivity on the wrong channel is wrong by the
    ratio between the two -- five times, on this gateway -- while looking
    entirely ordinary.
    """
    if not raw or not str(raw).strip():
        return []

    values: list[Optional[float]] = []
    for piece in str(raw).split(","):
        piece = piece.strip()
        if not piece:
            values.append(None)
            continue
        try:
            number = float(piece)
        except ValueError:
            warnings.append(
                f"Sensitivity list contains {piece!r}, which is not a number. "
                f"The whole list was ignored rather than partly applied."
            )
            return []
        if not 0 < number <= MAX_SENSITIVITY_MV_PER_G:
            warnings.append(
                f"Sensitivity {number:g} mV/g is outside the plausible range "
                f"(0, {MAX_SENSITIVITY_MV_PER_G:g}]. The whole list was ignored."
            )
            return []
        values.append(number)

    if len(values) != channel_count:
        warnings.append(
            f"{len(values)} sensitivities were declared for {channel_count} "
            f"channels. The list was ignored rather than padded or truncated: "
            f"a figure on the wrong channel is wrong by the ratio between the "
            f"two and looks entirely ordinary."
        )
        return []
    return values


def _merge_channel_map(existing: Any, sensitivities: list[Optional[float]]) -> tuple[list[dict], int]:
    """Put each sensitivity on its channel, leaving the rest of the entry alone.

    The channel map already describes each channel's wiring -- axis, signal
    type, label -- and is the record the rest of the platform reads. This adds
    a field to it rather than creating a second place where channel facts live.

    Entries are 1-based (CH1 = 1), matching ChannelMapEntry and what
    `sensitivity_for_channel` expects.
    """
    by_index: dict[int, dict] = {}
    for entry in (existing if isinstance(existing, list) else []):
        if isinstance(entry, dict) and entry.get("channel_index") is not None:
            by_index[int(entry["channel_index"])] = dict(entry)

    updated = 0
    for zero_based, value in enumerate(sensitivities):
        if value is None:
            continue
        one_based = zero_based + 1
        entry = by_index.get(one_based) or {
            "channel_index": one_based,
            "machine_axis": "VERTICAL",
            "signal_type": "VIBRATION",
            "label": None,
        }
        if entry.get("sensitivity_mv_per_g") != value:
            updated += 1
        entry["sensitivity_mv_per_g"] = value
        by_index[one_based] = entry

    return [by_index[i] for i in sorted(by_index)], updated


def record_declaration(
    db: Session,
    *,
    sensor,
    plot_config,
    sample_unit: Optional[str],
    sensitivity_csv: Optional[str],
    channel_count: int,
) -> DeclarationResult:
    """Store what this capture's device said about its own samples.

    Returns what was written plus any warnings, which the caller puts on the
    ingest acknowledgement. Never raises: a bad declaration must not lose a
    capture, because the samples are still worth keeping even when nobody can
    yet say what they are.
    """
    result = DeclarationResult()

    if sample_unit:
        unit = normalise_unit(sample_unit)
        if unit is None:
            result.warnings.append(
                f"The device declared its unit as {sample_unit!r}, which is not "
                f"a unit this platform recognises. It was not recorded, so the "
                f"sensor stays unconfirmed and severities stay withheld. "
                f"Recognised spellings include g, V and mm/s."
            )
        else:
            previous = sensor.signal_unit
            if previous and previous != UNCONFIRMED and previous != unit:
                result.unit_changed = True
                result.warnings.append(
                    f"This sensor was recorded as {previous!r} and the device "
                    f"now declares {unit!r}. The new value is stored because it "
                    f"is what the device sent, but a unit does not change by "
                    f"itself -- check whether the gateway was reconfigured or "
                    f"the transducer replaced. Every stored feature before this "
                    f"capture was read as {previous!r}."
                )
            sensor.signal_unit = unit
            sensor.unit_confirmed = True
            db.add(sensor)
            result.unit = unit

    sensitivities = parse_sensitivities(sensitivity_csv, channel_count, result.warnings)
    if sensitivities and plot_config is not None:
        merged, updated = _merge_channel_map(plot_config.channel_map, sensitivities)
        if updated:
            # Reassigned rather than mutated in place: SQLAlchemy does not see
            # an in-place change to a JSON column and the write is lost.
            plot_config.channel_map = merged
            db.add(plot_config)
        result.sensitivities = sensitivities
        result.channels_updated = updated

        distinct = {v for v in sensitivities if v is not None}
        if len(distinct) > 1 and sensor.sensitivity:
            result.warnings.append(
                f"Channel sensitivities are not uniform "
                f"({', '.join(f'{v:g}' for v in sensitivities)} mV/g) but the "
                f"sensor record carries a single {float(sensor.sensitivity):g}. "
                f"The per-channel figures are used; the sensor-level one remains "
                f"the fallback for channels that declare none."
            )
    elif sensitivities and plot_config is None:
        result.warnings.append(
            "Per-channel sensitivities were declared but this sensor has no "
            "plot configuration to hold them, so they were not stored."
        )

    return result
