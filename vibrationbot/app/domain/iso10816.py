"""ISO 10816-3 / 20816-3 vibration severity zones.

Given a broadband velocity reading (RMS, mm/s, 10-1000 Hz), a machine group,
and a foundation type, this returns the evaluation zone A/B/C/D and what the
standard says to do about it.

Deliberately a hardcoded table lookup. The zone boundaries are the numbers the
maintenance decision actually hangs on, so they must be deterministic and
unit-testable — never the output of a semantic search that could rank the wrong
table first. The ingested standard supplies the prose that the answer cites;
this supplies the verdict.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from app.domain.records import ComputationRecord, FormulaSource

DATA_PATH = Path(__file__).parent / "data" / "iso10816_3.json"

Zone = Literal["A", "B", "C", "D"]
Foundation = Literal["rigid", "flexible"]
MachineGroup = Literal[1, 2, 3, 4]

STANDARDS = {
    "10816-3": "ISO 10816-3:2009",
    "20816-3": "ISO 20816-3:2022",
}

# A value exactly on a boundary belongs to the lower zone.
BOUNDARY_CONVENTION = (
    "A value exactly on a boundary is assigned to the lower zone "
    "(e.g. 2.80 mm/s -> Zone B, 2.81 mm/s -> Zone C)."
)


@dataclass(frozen=True)
class SeverityResult:
    velocity_rms_mm_s: float
    zone: Zone
    zone_meaning: str
    action: str
    urgency: str
    machine_group: int
    group_name: str
    foundation: Foundation
    standard: str
    boundaries: dict[str, float]
    # Distance to the next zone up. Small margins are the interesting case —
    # "Zone B, but 0.05 mm/s from C" is a different message from "Zone B".
    margin_to_next_mm_s: float | None
    next_zone: Zone | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "velocity_rms_mm_s": self.velocity_rms_mm_s,
            "zone": self.zone,
            "zone_meaning": self.zone_meaning,
            "action": self.action,
            "urgency": self.urgency,
            "machine_group": self.machine_group,
            "foundation": self.foundation,
            "standard": self.standard,
            "boundaries_mm_s": self.boundaries,
            "margin_to_next_mm_s": self.margin_to_next_mm_s,
            "next_zone": self.next_zone,
        }


@lru_cache(maxsize=1)
def _reference_data() -> dict[str, Any]:
    with DATA_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def group_definitions() -> dict[str, dict[str, Any]]:
    return _reference_data()["groups"]


def infer_machine_group(
    power_kw: float | None,
    machine_type: str | None = None,
    integrated_driver: bool = False,
    shaft_height_mm: float | None = None,
) -> int | None:
    """Best-effort group from nameplate data.

    Pumps are their own groups in the standard regardless of size, split by
    whether the driver is integrated. Everything else falls back to rated
    power, or to shaft height for electrical machines. Returns ``None`` rather
    than guessing when there is nothing to go on — the caller then asks.
    """
    kind = (machine_type or "").strip().lower()

    if "pump" in kind:
        return 4 if integrated_driver else 3

    if power_kw is not None:
        if power_kw > 300:
            return 1
        if power_kw > 15:
            return 2
        # Below 15 kW the standard's Groups 1-4 do not apply.
        return None

    if shaft_height_mm is not None:
        if shaft_height_mm >= 315:
            return 1
        if shaft_height_mm >= 160:
            return 2

    return None


def severity_zone(
    velocity_rms_mm_s: float,
    machine_group: int,
    foundation: str,
    standard: str = "10816-3",
) -> SeverityResult:
    """Assign an evaluation zone to a broadband velocity reading."""
    if velocity_rms_mm_s < 0:
        raise ValueError("velocity_rms_mm_s cannot be negative")

    group_key = str(machine_group)
    data = _reference_data()
    if group_key not in data["velocity_rms_mm_s"]:
        raise ValueError(
            f"machine_group must be 1, 2, 3 or 4 (got {machine_group!r}). "
            "See ISO 10816-3 Clause 5 for the group definitions."
        )

    foundation_key = (foundation or "").strip().lower()
    if foundation_key not in ("rigid", "flexible"):
        raise ValueError(
            f"foundation must be 'rigid' or 'flexible' (got {foundation!r})"
        )

    if standard not in STANDARDS:
        raise ValueError(f"standard must be one of {sorted(STANDARDS)} (got {standard!r})")

    ab, bc, cd = data["velocity_rms_mm_s"][group_key][foundation_key]

    # Boundary convention: <= puts an exact boundary value in the lower zone.
    if velocity_rms_mm_s <= ab:
        zone, next_zone, next_boundary = "A", "B", ab
    elif velocity_rms_mm_s <= bc:
        zone, next_zone, next_boundary = "B", "C", bc
    elif velocity_rms_mm_s <= cd:
        zone, next_zone, next_boundary = "C", "D", cd
    else:
        zone, next_zone, next_boundary = "D", None, None

    zone_info = data["zones"][zone]
    group_info = data["groups"][group_key]

    return SeverityResult(
        velocity_rms_mm_s=velocity_rms_mm_s,
        zone=zone,  # type: ignore[arg-type]
        zone_meaning=zone_info["meaning"],
        action=zone_info["action"],
        urgency=zone_info["urgency"],
        machine_group=int(machine_group),
        group_name=group_info["name"],
        foundation=foundation_key,  # type: ignore[arg-type]
        standard=STANDARDS[standard],
        boundaries={"A/B": ab, "B/C": bc, "C/D": cd},
        margin_to_next_mm_s=(
            round(next_boundary - velocity_rms_mm_s, 4) if next_boundary is not None else None
        ),
        next_zone=next_zone,  # type: ignore[arg-type]
    )


def displacement_zone(*_args: Any, **_kwargs: Any) -> None:
    """Not implemented — intentionally.

    ISO 10816-3 also tabulates displacement limits in micrometres for Groups 1
    and 2. Those columns have not been transcribed, and writing them from
    memory is exactly the failure this module exists to prevent. Transcribe
    them from the ingested standard into iso10816_3.json first, then implement.
    """
    raise NotImplementedError(
        "Displacement zone limits are not transcribed yet. Use velocity "
        "(severity_zone) or read the displacement table from the indexed "
        "ISO 10816-3 document."
    )


def build_record(result: SeverityResult) -> ComputationRecord:
    return ComputationRecord(
        tool="iso_severity_zone",
        inputs={
            "velocity_rms_mm_s": result.velocity_rms_mm_s,
            "machine_group": result.machine_group,
            "foundation": result.foundation,
            "standard": result.standard,
        },
        outputs=result.as_dict(),
        formula=(
            f"Table lookup, {result.standard}: Group {result.machine_group} "
            f"({result.group_name}), {result.foundation} foundation -> "
            f"A/B={result.boundaries['A/B']}, B/C={result.boundaries['B/C']}, "
            f"C/D={result.boundaries['C/D']} mm/s RMS"
        ),
        formula_source=FormulaSource(
            kind="standard",
            ref=result.standard,
            query_hint=(
                "ISO 10816-3 evaluation zones vibration severity classification "
                "machine groups recommended action"
            ),
        ),
        assumptions=[
            "Reading is broadband velocity RMS over 10-1000 Hz measured on a "
            "non-rotating part (bearing housing), per the standard's measurement "
            "conditions. A reading taken over a different band or in a different "
            "unit is not comparable to these limits.",
            BOUNDARY_CONVENTION,
        ],
        confidence=1.0,
    )


def summarize(result: SeverityResult) -> str:
    lines = [
        f"{result.velocity_rms_mm_s:.2f} mm/s RMS -> ZONE {result.zone} "
        f"({result.standard}, Group {result.machine_group} — {result.group_name}, "
        f"{result.foundation} foundation)",
        f"Meaning: {result.zone_meaning}",
        f"Action:  {result.action}",
        f"Zone boundaries for this class: A/B={result.boundaries['A/B']}, "
        f"B/C={result.boundaries['B/C']}, C/D={result.boundaries['C/D']} mm/s RMS",
    ]
    if result.margin_to_next_mm_s is not None:
        lines.append(
            f"Margin to Zone {result.next_zone}: {result.margin_to_next_mm_s:.2f} mm/s"
        )
    return "\n".join(lines)
