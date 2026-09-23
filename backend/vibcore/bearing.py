"""Rolling-element bearing fault frequencies.

The four defect frequencies fall out of the kinematics of a rolling element
tracking between two races. With ``fr`` the shaft rate in Hz, ``n`` the rolling
element count, ``d`` the element diameter, ``D`` the pitch diameter, ``theta``
the contact angle, and ``r = (d/D)cos(theta)``:

    BPFO = (n/2)(1 - r) fr      ball pass frequency, outer race
    BPFI = (n/2)(1 + r) fr      ball pass frequency, inner race
    BSF  = (D/2d)(1 - r^2) fr   ball spin frequency
    FTF  = (1/2)(1 - r) fr      fundamental train (cage) frequency

Two consequences worth knowing when reading a spectrum:

* ``BPFO + BPFI == n * fr`` exactly, for any geometry. It is the cheapest
  possible check that a geometry or an implementation is sane.
* A ball defect strikes both races per revolution, so spectra usually show
  ``2 x BSF`` rather than BSF. Both are returned.

All four are non-synchronous — irrational multiples of running speed — which is
what distinguishes a bearing defect from unbalance or misalignment in the first
place.

Geometry resolution is tiered, catalog first, and never RAG first: a retrieval
miss must not be able to change a fault frequency.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from vibcore.records import ComputationRecord, FormulaSource

DATA_PATH = Path(__file__).parent / "data" / "bearings.json"

GeometrySource = Literal["catalog", "estimated", "user", "retrieved"]

# Empirical rules for deep-groove ball bearings, calibrated against the two
# fully documented entries in bearings.json (6203 and 6205) and cross-checked
# against published 6308/6312 geometry.
#
#   ball diameter  ~ 0.30 * (OD - bore)     within ~3%
#   pitch diameter ~ (bore + OD) / 2        within ~1.5%
#   ball count     ~ (pi * D / d) / 1.65    exact for 6203/6205/6308,
#                                            off by one for 6312
#
# Deliberately not extended to roller bearings: the ratios are genuinely
# different per type, and a ball-tuned rule applied to a spherical roller
# bearing would produce a confident wrong answer. Those fall through to the
# caller, which asks the user or falls back to the indexed catalogues.
_BALL_DIA_FRACTION = 0.30
_BALL_COUNT_DIVISOR = 1.65

_MANUFACTURER_RE = re.compile(
    r"^(SKF|FAG|NSK|NTN|KOYO|TIMKEN|INA|NACHI|ZKL|SNR|MRC|RHP)\b[\s\-]*",
    re.IGNORECASE,
)
# Trailing seal/shield/clearance/cage suffixes: 6205-2RS1/C3, 6205 ZZ, 6205 E.
_SUFFIX_RE = re.compile(
    r"[\s\-/]*(2RS\d?|RS\d?|2Z|ZZ|Z|2RSR|RSR|N|NR|M|E|EM|TN9?|C[0-5]|P[0-6]|J|JEM)+$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class BearingGeometry:
    """Internal geometry of a rolling-element bearing.

    ``source`` and ``confidence`` travel with the geometry all the way into the
    answer, because "BPFO is 104.6 Hz" and "BPFO is about 104.6 Hz if this is a
    9-ball bearing" are different claims and the user needs to know which one
    they are getting.
    """

    n_balls: int
    ball_dia_mm: float
    pitch_dia_mm: float
    contact_angle_deg: float = 0.0
    designation: str = ""
    kind: str = "unknown"
    source: GeometrySource = "user"
    confidence: float = 1.0
    assumptions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.n_balls <= 0:
            raise ValueError("n_balls must be positive")
        if self.ball_dia_mm <= 0:
            raise ValueError("ball_dia_mm must be positive")
        if self.pitch_dia_mm <= 0:
            raise ValueError("pitch_dia_mm must be positive")
        if self.ball_dia_mm >= self.pitch_dia_mm:
            raise ValueError("ball_dia_mm must be smaller than pitch_dia_mm")
        if not 0.0 <= self.contact_angle_deg <= 90.0:
            raise ValueError("contact_angle_deg must be within [0, 90]")

    @property
    def ratio(self) -> float:
        """``r = (d/D)cos(theta)`` — the only geometry term the formulas need."""
        return (self.ball_dia_mm / self.pitch_dia_mm) * math.cos(
            math.radians(self.contact_angle_deg)
        )


@dataclass(frozen=True)
class FaultFrequencies:
    """Defect frequencies in Hz, with their orders of running speed.

    Analysts read spectra in orders, so both are always returned: 3.585x is
    recognisable across every speed the machine runs at, 104.56 Hz is not.
    """

    shaft_rpm: float
    shaft_hz: float
    bpfo_hz: float
    bpfi_hz: float
    bsf_hz: float
    bsf_2x_hz: float
    ftf_hz: float
    bpfo_order: float
    bpfi_order: float
    bsf_order: float
    bsf_2x_order: float
    ftf_order: float
    geometry: BearingGeometry

    def as_dict(self) -> dict[str, Any]:
        return {
            "shaft_rpm": round(self.shaft_rpm, 2),
            "shaft_hz": round(self.shaft_hz, 4),
            "BPFO_hz": round(self.bpfo_hz, 3),
            "BPFI_hz": round(self.bpfi_hz, 3),
            "BSF_hz": round(self.bsf_hz, 3),
            "2xBSF_hz": round(self.bsf_2x_hz, 3),
            "FTF_hz": round(self.ftf_hz, 3),
            "BPFO_order": round(self.bpfo_order, 4),
            "BPFI_order": round(self.bpfi_order, 4),
            "BSF_order": round(self.bsf_order, 4),
            "2xBSF_order": round(self.bsf_2x_order, 4),
            "FTF_order": round(self.ftf_order, 4),
        }

    def as_lines(self) -> list[str]:
        """Compact rendering for the string an LLM actually reads."""
        return [
            f"BPFO = {self.bpfo_hz:8.2f} Hz ({self.bpfo_order:.3f}x)",
            f"BPFI = {self.bpfi_hz:8.2f} Hz ({self.bpfi_order:.3f}x)",
            f"BSF  = {self.bsf_hz:8.2f} Hz ({self.bsf_order:.3f}x)"
            f"   [2xBSF = {self.bsf_2x_hz:.2f} Hz ({self.bsf_2x_order:.3f}x)]",
            f"FTF  = {self.ftf_hz:8.2f} Hz ({self.ftf_order:.3f}x)",
        ]


# --------------------------------------------------------------------------
# Core computation
# --------------------------------------------------------------------------


def fault_frequencies(geom: BearingGeometry, shaft_rpm: float) -> FaultFrequencies:
    """Compute BPFO/BPFI/BSF/FTF for a geometry at a given shaft speed."""
    if shaft_rpm <= 0:
        raise ValueError("shaft_rpm must be positive")

    fr = shaft_rpm / 60.0
    r = geom.ratio
    n = geom.n_balls
    d = geom.ball_dia_mm
    dp = geom.pitch_dia_mm

    bpfo = (n / 2.0) * (1.0 - r) * fr
    bpfi = (n / 2.0) * (1.0 + r) * fr
    bsf = (dp / (2.0 * d)) * (1.0 - r * r) * fr
    ftf = 0.5 * (1.0 - r) * fr

    return FaultFrequencies(
        shaft_rpm=shaft_rpm,
        shaft_hz=fr,
        bpfo_hz=bpfo,
        bpfi_hz=bpfi,
        bsf_hz=bsf,
        bsf_2x_hz=2.0 * bsf,
        ftf_hz=ftf,
        bpfo_order=bpfo / fr,
        bpfi_order=bpfi / fr,
        bsf_order=bsf / fr,
        bsf_2x_order=2.0 * bsf / fr,
        ftf_order=ftf / fr,
        geometry=geom,
    )


# --------------------------------------------------------------------------
# Geometry resolution
# --------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _reference_data() -> dict[str, Any]:
    with DATA_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def normalize_designation(designation: str) -> str:
    """Strip manufacturer prefix and seal/clearance suffix.

    "SKF 6205-2RS1/C3" and "6205 ZZ" both reduce to "6205", because none of
    that decoration changes the internal geometry.
    """
    text = (designation or "").strip().upper()
    text = _MANUFACTURER_RE.sub("", text)
    text = text.replace(" ", "")
    # Applied repeatedly: "6205-2RS1/C3" sheds one suffix group at a time.
    previous = None
    while previous != text:
        previous = text
        text = _SUFFIX_RE.sub("", text)
    return text.strip("-/ ")


def bore_from_code(bore_code: str) -> float | None:
    """ISO 15 bore code to bore diameter in mm.

    Codes 00-03 are special cases; 04 and up are simply the code times five.
    """
    if not bore_code.isdigit():
        return None
    special = {"00": 10.0, "01": 12.0, "02": 15.0, "03": 17.0}
    if bore_code in special:
        return special[bore_code]
    value = int(bore_code)
    if 4 <= value <= 96:
        return value * 5.0
    return None


def _split_designation(normalized: str) -> tuple[str, str] | None:
    """Split a normalized designation into (series, bore_code).

    Bearing designations put the bore code in the last two digits, with
    everything before it identifying the type and dimension series: 6205 is
    series 62 bore code 05; 22312 is series 223 bore code 12.
    """
    digits = re.sub(r"[^0-9]", "", normalized)
    if len(digits) < 3:
        return None
    return digits[:-2], digits[-2:]


def estimate_geometry(
    bore_mm: float,
    outside_dia_mm: float,
    n_balls: int | None = None,
    designation: str = "",
) -> BearingGeometry:
    """Estimate deep-groove ball geometry from boundary dimensions.

    Accurate to a few percent on ball and pitch diameter, and exact on ball
    count for the bearings it was calibrated against — but it can be off by one
    ball on larger sizes, which moves BPFO by roughly 11%. The returned
    geometry therefore carries confidence 0.6 and an assumption string that the
    generation prompt is required to surface.
    """
    if outside_dia_mm <= bore_mm:
        raise ValueError("outside_dia_mm must exceed bore_mm")

    ball_dia = _BALL_DIA_FRACTION * (outside_dia_mm - bore_mm)
    pitch_dia = (bore_mm + outside_dia_mm) / 2.0
    if n_balls is None:
        n_balls = max(3, round((math.pi * pitch_dia / ball_dia) / _BALL_COUNT_DIVISOR))

    return BearingGeometry(
        n_balls=n_balls,
        ball_dia_mm=round(ball_dia, 3),
        pitch_dia_mm=round(pitch_dia, 3),
        contact_angle_deg=0.0,
        designation=designation,
        kind="deep_groove_ball",
        source="estimated",
        confidence=0.6,
        assumptions=(
            f"Bearing geometry for {designation or 'this bearing'} was estimated from "
            f"standard boundary dimensions ({bore_mm:.0f} x {outside_dia_mm:.0f} mm), not "
            f"read from a manufacturer catalogue. Ball count ({n_balls}) may be off by "
            f"one, which would shift BPFO/BPFI by roughly 10%. Confirm against the "
            f"bearing datasheet before acting on a marginal match.",
        ),
    )


def resolve_bearing(designation: str) -> BearingGeometry | None:
    """Look up bearing geometry by designation.

    Tier 1 is the bundled catalogue of published internal geometry. Tier 2
    estimates from ISO boundary dimensions for deep-groove ball bearings only.
    Anything else returns ``None``, which the caller turns into either a request
    for the user's geometry or a retrieval against the indexed bearing
    catalogues — never a guess.
    """
    normalized = normalize_designation(designation)
    if not normalized:
        return None

    data = _reference_data()

    entry = data["catalog"].get(normalized)
    if entry is not None:
        return BearingGeometry(
            n_balls=entry["n_balls"],
            ball_dia_mm=entry["ball_dia_mm"],
            pitch_dia_mm=entry["pitch_dia_mm"],
            contact_angle_deg=entry.get("contact_angle_deg", 0.0),
            designation=normalized,
            kind=entry.get("kind", "deep_groove_ball"),
            source="catalog",
            confidence=1.0,
        )

    parts = _split_designation(normalized)
    if parts is None:
        return None
    series, bore_code = parts

    # Estimation is only defensible for deep-groove ball bearings.
    if series not in data["boundary_dimensions"]:
        return None

    dims = data["boundary_dimensions"][series].get(bore_code)
    if dims is None:
        # Not tabulated, but the bore code alone still gives the bore. Without
        # an outside diameter there is nothing to estimate from.
        return None

    bore_mm, outside_dia_mm, _width = dims
    return estimate_geometry(
        bore_mm=float(bore_mm),
        outside_dia_mm=float(outside_dia_mm),
        designation=normalized,
    )


def geometry_from_inputs(
    designation: str | None = None,
    n_balls: int | None = None,
    ball_dia_mm: float | None = None,
    pitch_dia_mm: float | None = None,
    contact_angle_deg: float = 0.0,
) -> BearingGeometry | None:
    """Build geometry from whatever the caller supplied.

    Explicit geometry always wins over a designation lookup — if the user read
    the numbers off the bearing datasheet, they are better than anything this
    module can infer.
    """
    if n_balls and ball_dia_mm and pitch_dia_mm:
        return BearingGeometry(
            n_balls=n_balls,
            ball_dia_mm=ball_dia_mm,
            pitch_dia_mm=pitch_dia_mm,
            contact_angle_deg=contact_angle_deg,
            designation=normalize_designation(designation or ""),
            kind="user_supplied",
            source="user",
            confidence=1.0,
        )
    if designation:
        geom = resolve_bearing(designation)
        if geom is not None and contact_angle_deg:
            geom = replace(geom, contact_angle_deg=contact_angle_deg)
        return geom
    return None


# --------------------------------------------------------------------------
# Record construction
# --------------------------------------------------------------------------


def build_record(freqs: FaultFrequencies) -> ComputationRecord:
    """Wrap a result as an auditable ComputationRecord."""
    geom = freqs.geometry
    return ComputationRecord(
        tool="bearing_fault_frequencies",
        inputs={
            "designation": geom.designation or None,
            "shaft_rpm": round(freqs.shaft_rpm, 2),
            "n_balls": geom.n_balls,
            "ball_dia_mm": geom.ball_dia_mm,
            "pitch_dia_mm": geom.pitch_dia_mm,
            "contact_angle_deg": geom.contact_angle_deg,
            "geometry_source": geom.source,
        },
        outputs=freqs.as_dict(),
        formula="BPFO=(n/2)(1-r)fr, BPFI=(n/2)(1+r)fr, BSF=(D/2d)(1-r^2)fr, "
        "FTF=(1/2)(1-r)fr, where r=(d/D)cos(theta) and fr=RPM/60",
        formula_source=FormulaSource(
            kind="textbook",
            ref="Rolling-element bearing defect frequencies",
            query_hint="ball pass frequency outer race inner race cage formula derivation bearing",
        ),
        assumptions=[
            "Pure rolling contact, no sliding or slip. Real bearings slip by "
            "1-2%, so measured defect frequencies sit slightly below these "
            "values — match peaks within about +/-1.5%, not exactly.",
            *geom.assumptions,
        ],
        confidence=geom.confidence,
    )


def summarize(freqs: FaultFrequencies) -> str:
    """The compact string handed to the LLM."""
    geom = freqs.geometry
    label = geom.designation or "bearing"
    header = (
        f"{label} @ {freqs.shaft_rpm:.0f} rpm (fr = {freqs.shaft_hz:.3f} Hz) — "
        f"geometry: {geom.n_balls} elements, d={geom.ball_dia_mm:.2f} mm, "
        f"D={geom.pitch_dia_mm:.2f} mm, angle={geom.contact_angle_deg:.0f} deg "
        f"[{geom.source}]"
    )
    lines = [header, *freqs.as_lines()]
    if geom.source == "estimated":
        lines.append(
            "NOTE: geometry estimated from boundary dimensions — treat as approximate."
        )
    return "\n".join(lines)
