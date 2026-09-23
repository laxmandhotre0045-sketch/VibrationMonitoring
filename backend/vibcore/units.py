"""Amplitude conversion between acceleration, velocity, and displacement.

For a sinusoid at frequency ``f`` (omega = 2*pi*f) the three quantities are
related by differentiation and integration in time:

    a_pk = omega * v_pk = omega^2 * d_pk

so converting between them requires knowing the frequency. That is the whole
subtlety of this module, and the reason every result carries a warning: the
relation is *exact only at a single frequency*. Applying it to a broadband
overall reading treats all the energy as though it sat at one frequency, which
it does not. Broadband integration must be done in the frequency domain — see
``app/domain/signal.py``.

Measure conversion (RMS / peak / peak-to-peak) assumes a sinusoid too:
``peak = sqrt(2) * rms`` and ``pk-pk = 2 * peak``. For a real signal with a
crest factor other than 1.414 these are approximations, which is why the crest
factor is worth computing separately.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

from vibcore.records import ComputationRecord, FormulaSource

Unit = Literal["g", "m/s2", "mm/s", "in/s", "um", "mil", "mm"]
Measure = Literal["rms", "peak", "pk-pk"]

G_TO_MM_S2 = 9806.65  # standard gravity, mm/s^2
MM_TO_IN = 1.0 / 25.4
UM_PER_MIL = 25.4

# Which physical quantity each unit measures — conversion between quantities
# needs a frequency, conversion within one does not.
_QUANTITY: dict[str, str] = {
    "g": "acceleration",
    "m/s2": "acceleration",
    "mm/s": "velocity",
    "in/s": "velocity",
    "um": "displacement",
    "mm": "displacement",
    "mil": "displacement",
}

# Everything is converted through a canonical SI-ish unit per quantity:
# acceleration in mm/s^2, velocity in mm/s, displacement in um.
_TO_CANONICAL: dict[str, float] = {
    "g": G_TO_MM_S2,
    "m/s2": 1000.0,
    "mm/s": 1.0,
    "in/s": 25.4,
    "um": 1.0,
    "mm": 1000.0,
    "mil": UM_PER_MIL,
}

_CANONICAL_NAME = {
    "acceleration": "mm/s^2",
    "velocity": "mm/s",
    "displacement": "um",
}

# Multiplier from a given measure to peak.
_TO_PEAK: dict[str, float] = {
    "rms": math.sqrt(2.0),
    "peak": 1.0,
    "pk-pk": 0.5,
}


@dataclass(frozen=True)
class ConversionResult:
    value: float
    from_unit: str
    from_measure: str
    to_unit: str
    to_measure: str
    frequency_hz: float | None
    quantity_changed: bool
    warnings: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "value": round(self.value, 6),
            "unit": self.to_unit,
            "measure": self.to_measure,
            "from_unit": self.from_unit,
            "from_measure": self.from_measure,
            "frequency_hz": self.frequency_hz,
        }


def _normalize_unit(unit: str) -> str:
    key = (unit or "").strip().lower().replace("µ", "u")
    aliases = {
        "g": "g",
        "gs": "g",
        "m/s^2": "m/s2",
        "m/s2": "m/s2",
        "ms2": "m/s2",
        "mm/s": "mm/s",
        "mms": "mm/s",
        "in/s": "in/s",
        "ips": "in/s",
        "um": "um",
        "micron": "um",
        "microns": "um",
        "mm": "mm",
        "mil": "mil",
        "mils": "mil",
    }
    if key not in aliases:
        raise ValueError(
            f"Unknown unit {unit!r}. Supported: g, m/s2, mm/s, in/s, um, mm, mil."
        )
    return aliases[key]


def _normalize_measure(measure: str) -> str:
    key = (measure or "").strip().lower().replace("_", "-").replace(" ", "")
    aliases = {
        "rms": "rms",
        "peak": "peak",
        "pk": "peak",
        "0-pk": "peak",
        "zero-peak": "peak",
        "pk-pk": "pk-pk",
        "pkpk": "pk-pk",
        "p-p": "pk-pk",
        "pp": "pk-pk",
        "peak-peak": "pk-pk",
        "peaktopeak": "pk-pk",
    }
    if key not in aliases:
        raise ValueError(
            f"Unknown measure {measure!r}. Supported: rms, peak, pk-pk."
        )
    return aliases[key]


def convert_amplitude(
    value: float,
    from_unit: str,
    to_unit: str,
    frequency_hz: float | None = None,
    from_measure: str = "rms",
    to_measure: str = "rms",
) -> ConversionResult:
    """Convert a vibration amplitude between units and measures.

    ``frequency_hz`` is required only when the physical quantity changes
    (acceleration <-> velocity <-> displacement); converting g to m/s^2, or RMS
    to peak, does not need it.
    """
    src_unit = _normalize_unit(from_unit)
    dst_unit = _normalize_unit(to_unit)
    src_measure = _normalize_measure(from_measure)
    dst_measure = _normalize_measure(to_measure)

    src_quantity = _QUANTITY[src_unit]
    dst_quantity = _QUANTITY[dst_unit]
    quantity_changed = src_quantity != dst_quantity

    if quantity_changed and (frequency_hz is None or frequency_hz <= 0):
        raise ValueError(
            f"Converting {src_quantity} ({src_unit}) to {dst_quantity} ({dst_unit}) "
            "requires a positive frequency_hz — the relation a = omega*v = omega^2*d "
            "is frequency dependent."
        )

    warnings: list[str] = []

    # 1. Normalise the measure to peak, so the quantity conversion is unambiguous.
    peak_value = value * _TO_PEAK[src_measure]

    # 2. Convert to this quantity's canonical unit.
    canonical = peak_value * _TO_CANONICAL[src_unit]

    # 3. Integrate or differentiate across quantities, if needed.
    if quantity_changed:
        omega = 2.0 * math.pi * float(frequency_hz)  # type: ignore[arg-type]
        # Canonical units are mm/s^2, mm/s, um — the 1000x is the mm->um step.
        if src_quantity == "acceleration" and dst_quantity == "velocity":
            canonical = canonical / omega
        elif src_quantity == "acceleration" and dst_quantity == "displacement":
            canonical = (canonical / (omega * omega)) * 1000.0
        elif src_quantity == "velocity" and dst_quantity == "acceleration":
            canonical = canonical * omega
        elif src_quantity == "velocity" and dst_quantity == "displacement":
            canonical = (canonical / omega) * 1000.0
        elif src_quantity == "displacement" and dst_quantity == "velocity":
            canonical = (canonical / 1000.0) * omega
        elif src_quantity == "displacement" and dst_quantity == "acceleration":
            canonical = (canonical / 1000.0) * omega * omega

        warnings.append(
            f"Converted {src_quantity} to {dst_quantity} at {frequency_hz:g} Hz. This is "
            "exact only for a single sinusoid at that frequency; applying it to a "
            "broadband overall reading treats all the energy as if it were at "
            f"{frequency_hz:g} Hz. For broadband data, integrate in the frequency domain."
        )

    # 4. Back out to the target unit and measure.
    result_peak = canonical / _TO_CANONICAL[dst_unit]
    result = result_peak / _TO_PEAK[dst_measure]

    if src_measure != dst_measure:
        warnings.append(
            f"Measure converted {src_measure} -> {dst_measure} assuming a sinusoid "
            "(peak = sqrt(2) x rms). For an impulsive signal with a high crest factor "
            "this understates the true peak."
        )

    return ConversionResult(
        value=result,
        from_unit=src_unit,
        from_measure=src_measure,
        to_unit=dst_unit,
        to_measure=dst_measure,
        frequency_hz=frequency_hz if quantity_changed else None,
        quantity_changed=quantity_changed,
        warnings=warnings,
    )


def build_record(result: ConversionResult, original_value: float) -> ComputationRecord:
    return ComputationRecord(
        tool="convert_amplitude",
        inputs={
            "value": original_value,
            "from_unit": result.from_unit,
            "from_measure": result.from_measure,
            "to_unit": result.to_unit,
            "to_measure": result.to_measure,
            "frequency_hz": result.frequency_hz,
        },
        outputs=result.as_dict(),
        formula=(
            "a_pk = omega*v_pk = omega^2*d_pk with omega = 2*pi*f; "
            "peak = sqrt(2)*rms; pk-pk = 2*peak; 1 g = 9806.65 mm/s^2; 1 mil = 25.4 um"
        ),
        formula_source=FormulaSource(
            kind="textbook",
            ref="Acceleration / velocity / displacement relationships",
            query_hint=(
                "relationship between acceleration velocity displacement vibration "
                "integration frequency domain units conversion"
            ),
        ),
        assumptions=result.warnings,
        # A same-quantity conversion is exact; a cross-quantity one leans on the
        # single-frequency assumption, which the user should weigh.
        confidence=0.8 if result.quantity_changed else 1.0,
    )


def summarize(result: ConversionResult, original_value: float) -> str:
    freq = f" @ {result.frequency_hz:g} Hz" if result.frequency_hz else ""
    lines = [
        f"{original_value:g} {result.from_unit} {result.from_measure}{freq}"
        f"  =  {result.value:.4g} {result.to_unit} {result.to_measure}"
    ]
    lines.extend(f"NOTE: {w}" for w in result.warnings)
    return "\n".join(lines)
