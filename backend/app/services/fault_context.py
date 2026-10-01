"""What the fault rules need from a capture — VIK-050 and VIK-052.

The fault-ranking engine in `vibcore.signatures` has been written and tested
since before this platform had anything to feed it. It wants two things: a
list of spectral peaks with their orders, and a description of the machine
those peaks came off. This module produces both, and produces neither by
inventing anything.

**Nothing here is a second implementation.** The peak finder is
`waterfall.detect_spectrum_peaks`, already tuned to 8% prominence and
already what the waterfall chart shows a user -- so a peak the rules fire on
is a peak somebody can see on screen. A second finder with its own
thresholds would eventually disagree with the picture, and the disagreement
would be invisible: the chart would show one thing and the diagnosis would
rest on another.

**The machine description comes out of the database, not off an operator.**
Rated speed, pole count, vanes, blades, gear teeth, bearings and foundation
are all recorded against the equipment already. The report tool asks a
person to type three of them in, which is three chances to disagree with
the record and no way to tell afterwards which was used.

**A missing detail disables a rule rather than weakening it.** A machine
with no gearbox recorded gets no gear-mesh hypothesis at all -- not a
gear-mesh hypothesis computed against a guessed tooth count. The engine is
built for that: `MachineContext` leaves unknown fields empty and the rules
that need them stand down.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

import numpy as np

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.waterfall import detect_spectrum_peaks
from vibcore.signatures import MachineContext, SpectralPeak, assign_orders

logger = logging.getLogger(__name__)

#: Peaks handed to the rules per channel.
#:
#: Higher than the waterfall chart's default of eight. The chart is drawn for
#: a person, who reads the tallest few; the rules are looking for a specific
#: order that may sit well down the list -- a bearing outer-race line at
#: 3.57x is often smaller than 1x and 2x and every mains harmonic, and it is
#: the one that names the fault.
MAX_PEAKS = 20

#: Axis names the rules understand, from how a sensor is mounted. The engine
#: penalises a hypothesis that needs axial evidence when none was measured
#: (NO_AXIAL_PENALTY), so getting this wrong turns a real misalignment
#: finding into a weak one.
_DIRECTIONS = {
    "horizontal": "horizontal", "h": "horizontal",
    "vertical": "vertical", "v": "vertical",
    "axial": "axial", "a": "axial",
}


def direction_for_channel(db: Session, sensor_id: UUID, channel: int) -> str:
    """Which way this channel's transducer points, or empty if nobody said.

    Empty rather than a guess. The engine treats an unknown direction as
    "not measured", which is what it is -- and a channel wrongly called
    axial would manufacture the evidence a misalignment rule looks for.
    """
    try:
        row = db.execute(text("""
            SELECT channel_map FROM plot_configurations WHERE sensor_id = :s
        """), {"s": str(sensor_id)}).fetchone()
        entries = row.channel_map if row and isinstance(row.channel_map, list) else []
        for entry in entries:
            if int(entry.get("channel_index", -1)) != channel + 1:
                continue
            axis = (entry.get("machine_axis") or "").strip().lower()
            return _DIRECTIONS.get(axis, "")

        sensor = db.execute(text("""
            SELECT orientation FROM sensor_configurations WHERE id = :s
        """), {"s": str(sensor_id)}).fetchone()
        if sensor and sensor.orientation:
            return _DIRECTIONS.get(sensor.orientation.strip().lower(), "")
    except Exception:
        logger.exception("Could not resolve direction for channel %s", channel)
    return ""


def peaks_from_spectrum(
    freqs: np.ndarray,
    mags: np.ndarray,
    *,
    shaft_hz: Optional[float] = None,
    direction: str = "",
    max_peaks: int = MAX_PEAKS,
) -> list[SpectralPeak]:
    """VIK-050: one spectrum, as the peak list the rules expect.

    Orders are filled in only when a shaft speed was actually established.
    Without one the peaks still carry their frequencies and the engine
    declines to rank anything -- which is right, because every rule in the
    table is written in orders, and an order computed against a guessed
    speed is wrong by exactly the ratio of the guess.
    """
    found = detect_spectrum_peaks(freqs, mags, max_peaks=max_peaks)
    peaks = [
        SpectralPeak(frequency_hz=p["frequency"], amplitude=p["amplitude"],
                     direction=direction, source="auto")
        for p in found
    ]
    if shaft_hz and shaft_hz > 0:
        peaks = assign_orders(peaks, shaft_hz * 60.0)
    return peaks


def machine_context(
    db: Session,
    equipment_id: Optional[UUID],
    *,
    shaft_rpm: Optional[float] = None,
    bearing_orders: Optional[dict[str, Any]] = None,
    line_frequency_hz: float = 50.0,
) -> MachineContext:
    """VIK-052: everything the rules need about the machine, from the record.

    `line_frequency_hz` defaults to 50 because this plant is in India. It
    only matters for the electrical rule, which looks for sidebands at twice
    line frequency around running speed.
    """
    context = MachineContext(shaft_rpm=shaft_rpm)

    if bearing_orders:
        context.bearing_orders = {
            name: float(value)
            for name, value in bearing_orders.items()
            if name in ("ftf", "bsf", "bpfo", "bpfi") and value
        }

    if equipment_id is None:
        return context

    try:
        row = db.execute(text("""
            SELECT motor_pole_count, pump_vanes, fan_blades, gear_teeth,
                   gearbox_ratio, foundation_type, bearing_number_de,
                   rated_rpm
              FROM equipment_masters WHERE id = :e
        """), {"e": str(equipment_id)}).fetchone()
    except Exception:
        logger.exception("Could not read machine details for %s", equipment_id)
        return context
    if row is None:
        return context

    # The motor, for the rotor-bar rule. Its sidebands sit either side of
    # running speed at the pole-pass frequency, which is slip times poles --
    # so the rule needs the pole count and the synchronous speed, and is
    # skipped rather than guessed when either is absent.
    if row.motor_pole_count:
        context.motor_pole_count = int(row.motor_pole_count)
        # Synchronous speed from the supply: 120 f / poles.
        context.sync_rpm = 120.0 * line_frequency_hz / int(row.motor_pole_count)

    # Vane or blade pass: the count of vanes or blades, in orders of running
    # speed. A pump has vanes, a fan has blades, and a machine recorded with
    # neither gets no blade-pass rule rather than a default count.
    count = row.pump_vanes or row.fan_blades
    if count:
        context.vane_pass_order = float(count)

    # Gear mesh: teeth times running speed. `gear_teeth` alone gives the
    # first mesh order; the ratio is not needed for that and is not guessed
    # at when absent.
    if row.gear_teeth:
        context.gear_mesh_orders = [float(row.gear_teeth)]

    # Electrical rules key on line frequency, which is a property of the
    # supply rather than the machine. The pole count decides whether a
    # motor's own rules apply at all.
    if row.motor_pole_count:
        context.line_freq_hz = float(line_frequency_hz)

    # A rolling-element bearing is the default because that is what this
    # plant runs; a journal bearing changes which instability rules apply,
    # and it is named in the bearing field when present.
    details = (row.bearing_number_de or "").lower()
    if any(word in details for word in ("journal", "sleeve", "babbitt")):
        context.has_journal_bearings = True
        context.has_rolling_bearings = False

    return context


def context_completeness(context: MachineContext) -> dict[str, Any]:
    """What the rules can and cannot look for on this machine.

    Returned so a finding can say which families were never in the running.
    "No gear-mesh fault found" and "nobody recorded a tooth count, so gear
    mesh was never checked" are different statements, and only the first is
    reassuring.
    """
    available = {
        "shaft_speed": context.shaft_rpm is not None,
        "motor_slip": context.pole_pass_order is not None,
        "bearing_orders": bool(context.bearing_orders),
        "vane_or_blade_pass": context.vane_pass_order is not None,
        "gear_mesh": bool(context.gear_mesh_orders),
        "electrical": context.line_freq_hz is not None,
        "belt": context.belt_order is not None,
    }
    return {
        "available": sorted(k for k, v in available.items() if v),
        "missing": sorted(k for k, v in available.items() if not v),
    }
