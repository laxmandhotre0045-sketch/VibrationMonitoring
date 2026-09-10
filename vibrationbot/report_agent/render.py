"""Rendering and verification.

Two jobs, deliberately together: a report is rendered and then checked, and
the check must run on what was actually produced rather than on the data that
went in.

The verifier answers three questions, and a failure blocks the report rather
than footnoting it:

* Did every ``{{F#}}`` resolve? An unresolved placeholder reaching a customer
  is worse than no report.
* Does every fact the narrative cites exist in the ledger?
* Did anything write a bare number into prose instead of referencing a fact?

That last one matters most, and is the reason the ledger exists. In phase 1
the narrative is template-driven so it cannot fail, but the check is written
now, against the template, so that phase 3 -- where a model writes the prose --
inherits a verifier that was already true.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from report_agent.ledger import Ledger

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"

#: Table cells, dates and ids are full of digits that are not claims. The
#: bare-number check therefore runs on narrative prose only -- the sections a
#: model will eventually write -- not on the whole rendered document.
_NARRATIVE_HEADINGS = ("## 1. Summary",)


@dataclass
class Verification:
    ok: bool
    unresolved: list[str] = field(default_factory=list)
    unknown_refs: list[str] = field(default_factory=list)
    bare_numbers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def problems(self) -> list[str]:
        out: list[str] = []
        for ref in self.unresolved:
            out.append(f"UNRESOLVED PLACEHOLDER {ref} - no such fact in the ledger")
        for ref in self.unknown_refs:
            out.append(f"UNKNOWN FACT {ref} - referenced but never registered")
        for number in self.bare_numbers:
            out.append(
                f"BARE NUMBER {number!r} in narrative - every quantity must come "
                "from the ledger, not be typed into prose"
            )
        return out


def _ref(fact_id: str | None) -> str:
    """Emit a ledger placeholder from a template.

    A template writes ``{{ ref(assessment.critical_fact) }}`` rather than the
    number itself, which renders as ``{{F5}}`` and is then substituted from the
    ledger. It reads as an explicit request for a fact, and the verifier's
    bare-number check stays meaningful: any digit that reaches the narrative
    without going through here was typed by hand.
    """
    return f"{{{{{fact_id}}}}}" if fact_id else "(not recorded)"


def _environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(enabled_extensions=("html",), default=False),
        undefined=StrictUndefined,   # a missing variable is a bug, not a blank
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.globals["ref"] = _ref
    return env


@dataclass
class Rendered:
    """A report in both states, because the checks need different ones.

    ``raw`` still carries ``{{F#}}`` placeholders and is what the bare-number
    check must read: after substitution every ledger value is a digit in the
    text, so checking the finished document would flag the ledger's own output
    and prove nothing. The first version of this did exactly that.
    """

    text: str
    raw: str
    missing: list[str] = field(default_factory=list)


def render(ledger: Ledger, data: dict[str, Any], template: str = "report.md.j2") -> Rendered:
    """Render one report from the ledger and the pipeline's collected data."""
    dataset = data.get("dataset") or {}
    context = {
        "identity": dataset.get("identity") or {},
        "dataset": dataset,
        "features": data.get("features") or [],
        "iso": data.get("iso") or {},
        "integrity": data.get("integrity") or {},
        "calibration": data.get("calibration") or {},
        "shaft": data.get("shaft") or {},
        "velocity": data.get("velocity") or {},
        "assessment": data.get("assessment") or {},
        "meta": data.get("meta") or {},
        "facts": [f.as_dict() for f in ledger.all()],
        "caveats": ledger.caveats(),
    }
    raw = _environment().get_template(template).render(**context)
    resolved, missing = ledger.substitute(raw)
    if missing:
        logger.warning("Unresolved placeholders in report: %s", missing)
    return Rendered(text=resolved, raw=raw, missing=missing)


def verify(ledger: Ledger, rendered: Rendered) -> Verification:
    """Check a rendered report against the ledger that produced it.

    Unresolved placeholders are looked for in the finished text; bare numbers
    in the raw text, before substitution, where a hand-typed figure is still
    distinguishable from a ledger value.
    """
    unresolved = sorted(set(re.findall(r"\{\{\s*(F\d+)\s*\}\}", rendered.text)))
    unknown = [ref for ref in ledger.referenced(rendered.raw) if ledger.get(ref) is None]

    narrative = _narrative_only(rendered.raw)
    bare = Ledger.bare_numbers(narrative)

    notes: list[str] = []
    if not len(ledger):
        notes.append("The ledger is empty; this report asserts nothing.")

    return Verification(
        ok=not (unresolved or unknown or bare),
        unresolved=unresolved,
        unknown_refs=unknown,
        bare_numbers=sorted(set(bare)),
        notes=notes,
    )


def _narrative_only(rendered: str) -> str:
    """The prose sections, without tables, headings or the provenance list.

    A table cell holding "0.42409" is the ledger's own rendered value arriving
    where it belongs; flagging it would make the check useless. What must stay
    clean is the prose a human or a model writes around those tables.
    """
    lines: list[str] = []
    capturing = False
    for line in rendered.splitlines():
        if line.startswith("## "):
            capturing = any(line.startswith(h) for h in _NARRATIVE_HEADINGS)
            continue
        if not capturing:
            continue
        stripped = line.strip()
        if stripped.startswith("|") or stripped.startswith(">"):
            continue
        lines.append(line)
    return "\n".join(lines)
