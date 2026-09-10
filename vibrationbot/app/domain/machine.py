"""Machine asset profile and its derived forcing frequencies.

A profile is registered once and reused by every later analysis, which is what
lets "analyse 3H on P-101" work with no further input: shaft speed, bearing
designations, vane count, gear teeth, supply frequency and ISO group all resolve
from storage.

:func:`derived_frequencies` is the payoff. It computes every frequency the
machine is *capable* of producing before anything is measured, so an anonymous
peak at 172.7 Hz stops being "a peak" and becomes "7x — vane pass on the pump".
Matching observed peaks against a precomputed forcing-frequency table is how an
analyst reads a spectrum, and it is the difference between listing numbers and
diagnosing a machine.

Everything is optional. A profile with nothing but a running speed still yields
1x/2x/3x; each additional field switches on the frequencies that depend on it.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.domain import bearing as bearing_mod
from app.domain.iso10816 import infer_machine_group
from app.config import MACHINES_DIR

MACHINE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")

Foundation = Literal["rigid", "flexible"]
Direction = Literal["H", "V", "A", ""]


# --------------------------------------------------------------------------
# Profile model
# --------------------------------------------------------------------------


class Driver(BaseModel):
    kind: str = "motor"
    power_kw: float | None = None
    poles: int | None = None
    line_freq_hz: float | None = None
    rated_rpm: float | None = None
    vfd: bool = False
    shaft_height_mm: float | None = None


class Driven(BaseModel):
    kind: str = ""
    rated_rpm: float | None = None
    n_vanes: int | None = None
    n_blades: int | None = None
    integrated_driver: bool = False


class Coupling(BaseModel):
    kind: Literal["direct", "belt", "gear", "fluid", ""] = "direct"
    # Driver rpm / driven rpm. 1.0 for a direct coupling.
    ratio: float = 1.0
    # Belt drives only. Belt frequency needs the belt length and one sheave.
    belt_length_mm: float | None = None
    driver_sheave_dia_mm: float | None = None
    driven_sheave_dia_mm: float | None = None


class GearStage(BaseModel):
    teeth_in: int
    teeth_out: int
    name: str = ""


class Gearbox(BaseModel):
    stages: list[GearStage] = Field(default_factory=list)


class BearingSlot(BaseModel):
    """A bearing position on the machine.

    ``shaft`` says which shaft it turns with, so a gearbox output bearing gets
    its fault frequencies from the output speed rather than the input speed.
    """

    position: str
    designation: str = ""
    shaft: Literal["driver", "driven"] = "driver"
    n_balls: int | None = None
    ball_dia_mm: float | None = None
    pitch_dia_mm: float | None = None
    contact_angle_deg: float = 0.0
    kind: Literal["rolling", "journal"] = "rolling"


class MeasurementPoint(BaseModel):
    point_id: str
    location: str = ""
    direction: Direction = ""
    sensor: str = "accelerometer"
    mount: str = ""


class MachineProfile(BaseModel):
    machine_id: str
    name: str = ""
    type: str = ""
    driver: Driver = Field(default_factory=Driver)
    driven: Driven = Field(default_factory=Driven)
    coupling: Coupling = Field(default_factory=Coupling)
    gearbox: Gearbox | None = None
    foundation: Foundation = "rigid"
    iso_group: int | None = None
    bearings: list[BearingSlot] = Field(default_factory=list)
    points: list[MeasurementPoint] = Field(default_factory=list)
    notes: str = ""

    def resolved_iso_group(self) -> int | None:
        """Stated group if present, otherwise inferred from nameplate data."""
        if self.iso_group:
            return self.iso_group
        return infer_machine_group(
            power_kw=self.driver.power_kw,
            machine_type=self.type or self.driven.kind,
            integrated_driver=self.driven.integrated_driver,
            shaft_height_mm=self.driver.shaft_height_mm,
        )

    def point(self, point_id: str) -> MeasurementPoint | None:
        for candidate in self.points:
            if candidate.point_id.lower() == (point_id or "").lower():
                return candidate
        return None

    def bearing_at(self, location: str) -> BearingSlot | None:
        key = (location or "").strip().lower()
        for slot in self.bearings:
            if slot.position.strip().lower() == key:
                return slot
        return None

    def has_journal_bearings(self) -> bool:
        return any(b.kind == "journal" for b in self.bearings)

    def has_rolling_bearings(self) -> bool:
        return any(b.kind == "rolling" for b in self.bearings) or not self.bearings


# --------------------------------------------------------------------------
# Forcing frequencies
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ForcingFrequency:
    """One frequency this machine can produce, and where it came from."""

    key: str
    label: str
    hz: float
    order: float
    shaft: str
    kind: str
    source_field: str
    confidence: float = 1.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "hz": round(self.hz, 3),
            "order": round(self.order, 4),
            "shaft": self.shaft,
            "kind": self.kind,
            "source_field": self.source_field,
            "confidence": self.confidence,
        }


def shaft_speeds(profile: MachineProfile, actual_rpm: float | None = None) -> dict[str, float]:
    """Running speed of each shaft, in rpm.

    ``actual_rpm`` is the measured driver speed and always wins over the
    nameplate: fault frequencies scale with true running speed, and an induction
    motor under load runs a few percent below its rated speed. Using the
    nameplate would shift every computed frequency by that same few percent —
    enough to miss a +/-1.5% bearing match.
    """
    driver_rpm = actual_rpm or profile.driver.rated_rpm or profile.driven.rated_rpm
    if not driver_rpm:
        return {}

    speeds = {"driver": float(driver_rpm)}

    ratio = profile.coupling.ratio or 1.0
    if profile.gearbox and profile.gearbox.stages:
        # Overall reduction is the product of the stage ratios.
        gear_ratio = 1.0
        for stage in profile.gearbox.stages:
            if stage.teeth_in and stage.teeth_out:
                gear_ratio *= stage.teeth_out / stage.teeth_in
        speeds["driven"] = float(driver_rpm) / gear_ratio if gear_ratio else float(driver_rpm)
    elif profile.coupling.kind == "belt" and profile.coupling.driver_sheave_dia_mm and profile.coupling.driven_sheave_dia_mm:
        speeds["driven"] = float(driver_rpm) * (
            profile.coupling.driver_sheave_dia_mm / profile.coupling.driven_sheave_dia_mm
        )
    elif ratio and ratio != 1.0:
        speeds["driven"] = float(driver_rpm) / ratio
    else:
        speeds["driven"] = float(driver_rpm)

    return speeds


def _bearing_geometry(slot: BearingSlot) -> bearing_mod.BearingGeometry | None:
    return bearing_mod.geometry_from_inputs(
        designation=slot.designation or None,
        n_balls=slot.n_balls,
        ball_dia_mm=slot.ball_dia_mm,
        pitch_dia_mm=slot.pitch_dia_mm,
        contact_angle_deg=slot.contact_angle_deg,
    )


def derived_frequencies(
    profile: MachineProfile,
    point_id: str | None = None,
    actual_rpm: float | None = None,
) -> dict[str, ForcingFrequency]:
    """Every forcing frequency this machine can produce, keyed for lookup.

    ``point_id`` narrows bearing frequencies to the bearing at that measurement
    point when the point maps to a known location; otherwise all bearings are
    included, prefixed by position.
    """
    speeds = shaft_speeds(profile, actual_rpm)
    if not speeds:
        return {}

    driver_hz = speeds["driver"] / 60.0
    driven_hz = speeds.get("driven", speeds["driver"]) / 60.0
    # Orders are always expressed against the driver shaft, because that is what
    # a tachometer on the motor reports and what an analyser normalises to.
    reference_hz = driver_hz

    out: dict[str, ForcingFrequency] = {}

    def add(key, label, hz, shaft, kind, source_field, confidence=1.0):
        out[key] = ForcingFrequency(
            key=key,
            label=label,
            hz=hz,
            order=hz / reference_hz if reference_hz else 0.0,
            shaft=shaft,
            kind=kind,
            source_field=source_field,
            confidence=confidence,
        )

    for n in (1, 2, 3):
        add(f"{n}x", f"{n}x running speed", n * driver_hz, "driver", "synchronous",
            "driver.rated_rpm" if actual_rpm is None else "measured rpm")

    if abs(driven_hz - driver_hz) > 1e-9:
        add("driven_1x", "1x driven shaft", driven_hz, "driven", "synchronous", "coupling/gearbox ratio")

    # Vane / blade pass — a normal feature of the machine, not a fault by
    # itself; only a rise above baseline is diagnostic.
    if profile.driven.n_vanes:
        add("vane_pass", f"Vane pass ({profile.driven.n_vanes} vanes)",
            profile.driven.n_vanes * driven_hz, "driven", "forcing", "driven.n_vanes")
    if profile.driven.n_blades:
        add("blade_pass", f"Blade pass ({profile.driven.n_blades} blades)",
            profile.driven.n_blades * driven_hz, "driven", "forcing", "driven.n_blades")

    # Gear mesh. Each stage meshes at teeth x that shaft's rate; the input shaft
    # of stage 1 is the driver, and each subsequent stage runs slower.
    if profile.gearbox and profile.gearbox.stages:
        stage_input_hz = driver_hz
        for i, stage in enumerate(profile.gearbox.stages, start=1):
            if not (stage.teeth_in and stage.teeth_out):
                continue
            gmf = stage.teeth_in * stage_input_hz
            add(f"gmf_stage{i}", stage.name or f"Gear mesh stage {i} ({stage.teeth_in}T)",
                gmf, f"stage{i}", "forcing", f"gearbox.stages[{i - 1}]")
            stage_input_hz = stage_input_hz * stage.teeth_in / stage.teeth_out

    # Electrical. Pinned to supply frequency, not shaft speed — which is exactly
    # what makes it identifiable.
    line_hz = profile.driver.line_freq_hz
    if line_hz:
        add("line_2x", f"2x line frequency ({line_hz:g} Hz supply)",
            2.0 * line_hz, "electrical", "electrical", "driver.line_freq_hz")
        poles = profile.driver.poles
        if poles:
            sync_rpm = 120.0 * line_hz / poles
            slip_hz = max(0.0, (sync_rpm - speeds["driver"]) / 60.0)
            if slip_hz > 0:
                add("pole_pass", f"Pole-pass ({poles} poles, slip {slip_hz:.3f} Hz)",
                    slip_hz * poles, "electrical", "electrical", "driver.poles")

    # Belt frequency: belt speed divided by belt length.
    cpl = profile.coupling
    if cpl.kind == "belt" and cpl.belt_length_mm and cpl.driver_sheave_dia_mm:
        import math

        belt_hz = (math.pi * cpl.driver_sheave_dia_mm * driver_hz) / cpl.belt_length_mm
        add("belt", "Belt frequency", belt_hz, "belt", "forcing", "coupling.belt_length_mm")

    # Bearing defect frequencies, per position.
    slots = profile.bearings
    if point_id:
        point = profile.point(point_id)
        if point and point.location:
            located = profile.bearing_at(point.location)
            if located is not None:
                slots = [located]

    for slot in slots:
        if slot.kind != "rolling":
            continue
        geom = _bearing_geometry(slot)
        if geom is None:
            continue
        rpm = speeds.get(slot.shaft, speeds["driver"])
        freqs = bearing_mod.fault_frequencies(geom, rpm)
        prefix = "" if len(slots) == 1 else f"{slot.position}."
        label_suffix = "" if len(slots) == 1 else f" @ {slot.position}"
        for key, hz in (
            ("bpfo", freqs.bpfo_hz),
            ("bpfi", freqs.bpfi_hz),
            ("bsf", freqs.bsf_hz),
            ("bsf2x", freqs.bsf_2x_hz),
            ("ftf", freqs.ftf_hz),
        ):
            add(
                f"{prefix}{key}",
                f"{key.upper()}{label_suffix} ({geom.designation or 'bearing'})",
                hz,
                slot.shaft,
                "bearing",
                f"bearings[{slot.position}].designation",
                geom.confidence,
            )

    return out


def bearing_orders_for(
    profile: MachineProfile, point_id: str | None = None, actual_rpm: float | None = None
) -> dict[str, float]:
    """Bearing fault orders in the flat form ``signatures.MachineContext`` wants."""
    freqs = derived_frequencies(profile, point_id=point_id, actual_rpm=actual_rpm)
    out: dict[str, float] = {}
    for key, freq in freqs.items():
        if freq.kind != "bearing":
            continue
        short = key.split(".")[-1]
        # First bearing wins when several are present and no point narrowed it.
        out.setdefault(short, freq.order)
    return out


def summarize_frequencies(freqs: dict[str, ForcingFrequency]) -> str:
    if not freqs:
        return "(No forcing frequencies — machine profile has no running speed.)"
    rows = sorted(freqs.values(), key=lambda f: f.order)
    width = max(len(f.label) for f in rows)
    lines = [f"{'FORCING FREQUENCY'.ljust(width)}   {'Hz':>10}   {'order':>8}"]
    for f in rows:
        flag = "" if f.confidence >= 1.0 else "  (estimated geometry)"
        lines.append(f"{f.label.ljust(width)}   {f.hz:10.2f}   {f.order:8.3f}{flag}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------


class MachineStore:
    """File-per-machine JSON store.

    Same shape as data/documents/: one directory per entity, no database. A
    lock guards writes because FastAPI runs sync handlers in a threadpool.
    """

    def __init__(self, root: Path | None = None) -> None:
        self._root = root or MACHINES_DIR
        self._lock = threading.Lock()

    def _path(self, machine_id: str) -> Path:
        if not MACHINE_ID_RE.match(machine_id or ""):
            raise ValueError(
                f"Invalid machine_id {machine_id!r}: use letters, digits, dot, dash "
                "or underscore, up to 64 characters."
            )
        return self._root / machine_id / "profile.json"

    def save(self, profile: MachineProfile) -> Path:
        path = self._path(profile.machine_id)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Write-then-rename so a crash mid-write cannot leave a truncated
            # profile that fails to parse on next load.
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
            tmp.replace(path)
        return path

    def load(self, machine_id: str) -> MachineProfile | None:
        path = self._path(machine_id)
        if not path.exists():
            return None
        with path.open(encoding="utf-8") as fh:
            return MachineProfile.model_validate(json.load(fh))

    def list_ids(self) -> list[str]:
        if not self._root.exists():
            return []
        return sorted(
            d.name for d in self._root.iterdir() if (d / "profile.json").exists()
        )

    def delete(self, machine_id: str) -> bool:
        path = self._path(machine_id)
        if not path.exists():
            return False
        with self._lock:
            path.unlink()
            try:
                path.parent.rmdir()
            except OSError:
                # Other artifacts alongside the profile; leave the directory.
                pass
        return True


machine_store = MachineStore()
