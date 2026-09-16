"""Answer ISO 10816-3 severity-limit questions, without a language model.

This was part of the knowledge-base agent and is now its own thing, because it
is a different kind of job. The knowledge-base agent reads books and reports
what they say. This one answers a question the books cannot be trusted to
answer, for a reason worth stating plainly:

The ingested copy of ISO 10816-3 covers Groups 1 and 2. Pumps are Groups 3 and
4. Asked for a pump's Zone B/C boundary, a model reading that document finds a
table, reads a number out of it, and reports it with complete confidence -- from
the wrong group. Handed the correct tables for Group 3 (2.3 / 4.5 / 7.1) and
Group 4 (1.4 / 2.8 / 4.5) side by side, it reported 2.8 for both.

So no model is involved here at all. The question is parsed by regular
expressions, the limits come from ``app/domain/iso10816`` -- unit-tested against
the published values, covering all four groups -- and the answer is assembled by
code. Every figure it prints is a lookup, not a generation.

The trade is deliberate: this agent understands far less than a model would,
but what it does say is right. When it cannot work out the machine group it
returns both candidates and says so, rather than guessing.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from iso_agent.tools import iso_zone_limits

logger = logging.getLogger(__name__)

#: A question asking for a severity limit rather than an explanation. Kept
#: broad: a missed match sends the reader back to the books, which is the
#: failure this agent exists to prevent.
ASKS_LIMIT_RE = re.compile(
    # "zone B/C", "zone B to C", "zone B/C boundary". The second "zone" is
    # optional: requiring it missed the phrasing an engineer actually uses,
    # which is the one form this agent most needs to catch.
    r"\b(zone\s*[a-d]\s*(to|/|-)\s*(zone\s*)?[a-d]\b|zone boundar|"
    r"(vibration|severity|acceptab\w+|allowab\w+|permissib\w+)\s+limit|"
    r"limit .*\b(mm/s|iso)\b|how (high|much) .*(too|acceptable)|"
    r"\biso\s*(10816|20816)\b.*\b(limit|boundar|zone|mm/s)\b|"
    # "is 4.9 mm/s acceptable / too high / ok" -- how an engineer actually asks,
    # and the reason a reading is being looked up at all. Missing this was the
    # first gap the pattern showed in testing.
    r"\b\d+(\.\d+)?\s*mm\s*/\s*s\b.{0,60}\b(acceptab\w+|ok\b|too high|"
    r"a problem|safe|allowable|within limits|good|bad)|"
    r"\b(acceptab\w+|too high|within limits)\b.{0,40}\b\d+(\.\d+)?\s*mm\s*/\s*s)",
    re.IGNORECASE,
)

_POWER_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(kw|mw|hp)\b", re.IGNORECASE)
_MACHINE_RE = re.compile(
    r"\b(pump|motor|fan|blower|compressor|turbine|generator|gearbox|machine)\b",
    re.IGNORECASE,
)
_FOUNDATION_RE = re.compile(r"\b(rigid|flexible)\b", re.IGNORECASE)
_INTEGRATED_RE = re.compile(r"\bintegrated\s+driver\b", re.IGNORECASE)
_SEPARATE_RE = re.compile(r"\bseparate\s+driver\b", re.IGNORECASE)
#: A reading the question wants graded, e.g. "is 4.9 mm/s acceptable".
_READING_RE = re.compile(r"(\d+(?:\.\d+)?)\s*mm\s*/\s*s", re.IGNORECASE)


@dataclass
class IsoQuery:
    """What the code managed to read out of the question."""

    machine_type: str = "machine"
    power_kw: float | None = None
    foundation: str | None = None
    integrated_driver: bool | None = None
    reading_mm_s: float | None = None

    def unknowns(self) -> list[str]:
        missing = []
        if self.power_kw is None:
            missing.append("rated power")
        if self.foundation is None:
            missing.append("foundation (rigid or flexible)")
        if self.machine_type.lower() == "pump" and self.integrated_driver is None:
            missing.append("driver arrangement (integrated or separate)")
        return missing


@dataclass
class IsoAnswer:
    ok: bool
    text: str
    query: IsoQuery | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


def parse_question(question: str) -> IsoQuery:
    """Read the machine's details out of plain English. No model involved."""
    q = IsoQuery()

    match = _POWER_RE.search(question)
    if match:
        value, unit = float(match.group(1)), match.group(2).lower()
        # hp -> kW uses the mechanical horsepower conversion, 1 hp = 0.7457 kW.
        q.power_kw = value * 1000 if unit == "mw" else value * 0.7457 if unit == "hp" else value

    machine = _MACHINE_RE.search(question)
    if machine:
        q.machine_type = machine.group(1).lower()

    foundation = _FOUNDATION_RE.search(question)
    if foundation:
        q.foundation = foundation.group(1).lower()

    if _INTEGRATED_RE.search(question):
        q.integrated_driver = True
    elif _SEPARATE_RE.search(question):
        q.integrated_driver = False

    reading = _READING_RE.search(question)
    if reading:
        q.reading_mm_s = float(reading.group(1))

    return q


def _zone_for(reading: float, boundaries: dict[str, float]) -> str:
    """Which zone a reading falls in.

    A value exactly on a boundary belongs to the lower zone, which is the
    convention the standard uses and the opposite of what a naive comparison
    gives.
    """
    ab = boundaries.get("A/B")
    bc = boundaries.get("B/C")
    cd = boundaries.get("C/D")
    if ab is not None and reading <= ab:
        return "A"
    if bc is not None and reading <= bc:
        return "B"
    if cd is not None and reading <= cd:
        return "C"
    return "D"


def _format(data: dict[str, Any], q: IsoQuery) -> str:
    """Assemble the answer text. Every number here came from the lookup."""
    lines: list[str] = ["ISO 10816-3 velocity zone boundaries", ""]

    if data.get("ambiguous"):
        lines += ["  " + " ".join(str(data["ambiguous"]).split()), ""]

    for entry in data.get("results", []):
        lines.append(f"  Group {entry['group']} - {entry['group_name']}, {entry['support']} support")
        if entry.get("scope"):
            lines.append(f"    {entry['scope']}")
        bounds = entry["boundaries_mm_s_rms"]
        lines.append(
            "    " + "     ".join(f"Zone {name}: {value} mm/s RMS" for name, value in bounds.items())
        )
        if q.reading_mm_s is not None:
            zone = _zone_for(q.reading_mm_s, bounds)
            lines.append(f"    -> {q.reading_mm_s:g} mm/s falls in Zone {zone}")
        lines.append("")

    if data.get("convention"):
        lines.append(f"  {data['convention']}")

    unknowns = q.unknowns()
    if unknowns:
        lines += [
            "",
            "  Not stated in the question, so every applicable table is shown: "
            + ", ".join(unknowns) + ".",
        ]

    lines += [
        "",
        "  Source: app/domain/iso10816, unit-tested against the published values.",
        "  Measured on non-rotating parts, broadband 10-1000 Hz, mm/s RMS.",
    ]
    return "\n".join(lines)


#: Said when the question is not about limits. Naming the other agent matters:
#: a reader who came here with a diagnostic question and got a bare refusal
#: has been helped less than one who is told where to go.
NOT_A_LIMITS_QUESTION = (
    "This agent answers one thing: ISO 10816-3 severity limits -- what level of "
    "vibration is acceptable for a given machine.\n\n"
    "That does not look like a limits question. For anything explanatory -- what "
    "a fault looks like, what a measurement means, why something happens -- ask "
    "the knowledge-base agent, which answers from the indexed books:\n"
    '    python -m kb_agent ask "<your question>"\n\n'
    "If you did mean a limits question, say so in the standard's terms, for "
    'example: "zone B/C boundary for a 55 kW pump with a separate driver on a '
    'rigid foundation".'
)


def answer(question: str) -> IsoAnswer:
    """Answer one limits question, or say why it cannot be answered."""
    if not question or not question.strip():
        return IsoAnswer(ok=False, text="", reason="No question given.")

    # Decline anything that is not a limits question. Without this the agent
    # answered "what is wrong with the big pump downstairs" with a full set of
    # boundary tables, because the question contains the word "pump" -- correct
    # numbers, to a question nobody asked. An agent that answers outside its
    # subject is a quieter version of the failure this one exists to prevent:
    # confident output where no judgement was actually applied.
    if not ASKS_LIMIT_RE.search(question):
        return IsoAnswer(
            ok=False,
            text="",
            query=parse_question(question),
            reason=NOT_A_LIMITS_QUESTION,
        )

    q = parse_question(question)
    try:
        raw = iso_zone_limits(
            machine_type=q.machine_type,
            power_kw=q.power_kw,
            foundation=q.foundation,
            integrated_driver=q.integrated_driver,
        )
        data = json.loads(raw)
    except Exception as exc:  # noqa: BLE001 - report, never raise at a caller
        logger.warning("ISO lookup failed: %s", exc)
        return IsoAnswer(ok=False, text="", query=q, reason=f"Lookup failed: {exc}")

    if data.get("error"):
        return IsoAnswer(ok=False, text="", query=q, payload=data, reason=str(data["error"]))

    return IsoAnswer(ok=True, text=_format(data, q), query=q, payload=data)
