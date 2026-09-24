"""The fact ledger: every number in a report, with where it came from.

This is the core of the design and the reason the package exists. A report is
mostly numbers, and this project has now measured, repeatedly, what happens
when a language model is allowed to produce one: a bearing formula silently
doubled, a severity limit taken from the wrong table, a standard's part number
invented. None of those were fabrications out of nothing -- each was a
plausible reading of real data -- and none was caught by reading the output.

So no number in a report is ever written by a model. Every quantity is
registered here first, with its provenance, and the narrative refers to it by
id. ``substitute`` then puts the values in. A model that types "4.5 mm/s"
instead of "{{F7}}" has produced text the verifier rejects, because a bare
figure in narrative cannot be traced to anything.

Three provenances, and the distinction is the point:

MEASURED
    A sensor reading the platform recorded. Carries the capture it came from
    and the platform's own caveats about units and baselines.
COMPUTED
    A value from ``app/domain`` -- bearing frequencies, ISO zones, unit
    conversions -- unit-tested against published references. Carries its
    inputs so the arithmetic can be redone by hand.
CITED
    A statement from the indexed books, with book, chapter and page.

A reader can tell at a glance whether a figure was observed, derived or read
somewhere, which is exactly the distinction that gets lost when a model writes
a report in fluent prose.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable


class Provenance(str, Enum):
    MEASURED = "measured"
    COMPUTED = "computed"
    CITED = "cited"


#: Rendered beside a value so the distinction survives into the page.
PROVENANCE_MARK = {
    Provenance.MEASURED: "M",
    Provenance.COMPUTED: "C",
    Provenance.CITED: "R",
}


@dataclass
class Fact:
    """One quantity, and everything needed to defend it."""

    id: str
    label: str
    value: Any
    unit: str
    provenance: Provenance
    source: str
    detail: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    caveats: list[str] = field(default_factory=list)

    def rendered(self) -> str:
        """The value as it should appear in prose, with its unit."""
        value = self.value
        if isinstance(value, float):
            # Three significant-ish decimals, trailing zeros trimmed. Vibration
            # features span 1e-3 to 1e2, so a fixed precision reads badly at
            # one end or loses information at the other.
            text = f"{value:.6g}"
        else:
            text = str(value)
        return f"{text} {self.unit}".strip()

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "value": self.value,
            "unit": self.unit,
            "rendered": self.rendered(),
            "provenance": self.provenance.value,
            "mark": PROVENANCE_MARK[self.provenance],
            "source": self.source,
            "detail": self.detail,
            "confidence": self.confidence,
            "caveats": self.caveats,
        }


#: "{{F12}}" -- the only way a narrative may refer to a quantity.
PLACEHOLDER_RE = re.compile(r"\{\{\s*(F\d+)\s*\}\}")

#: A bare number in narrative text. Deliberately broad: it is easier to
#: exempt a false positive than to notice a real one that slipped through.
#: Ordinals ("1X", "2X") and small counts in prose are excluded, because they
#: are language rather than data.
BARE_NUMBER_RE = re.compile(r"(?<![\w.{])(\d+(?:\.\d+)?)(?![\w}])")
_ORDER_RE = re.compile(r"\d+\s*[xX]\b")


class Ledger:
    """Every fact in one report, in the order they were established."""

    def __init__(self) -> None:
        self._facts: dict[str, Fact] = {}
        self._counter = 0

    # ------------------------------------------------------------ adding --

    def _next_id(self) -> str:
        self._counter += 1
        return f"F{self._counter}"

    def add(
        self,
        label: str,
        value: Any,
        unit: str,
        provenance: Provenance,
        source: str,
        *,
        detail: dict[str, Any] | None = None,
        confidence: float = 1.0,
        caveats: Iterable[str] = (),
    ) -> Fact:
        fact = Fact(
            id=self._next_id(),
            label=label,
            value=value,
            unit=unit,
            provenance=provenance,
            source=source,
            detail=dict(detail or {}),
            confidence=confidence,
            caveats=list(caveats),
        )
        self._facts[fact.id] = fact
        return fact

    def measured(self, label: str, value: Any, unit: str, source: str, **kw: Any) -> Fact:
        """A sensor reading the platform recorded."""
        return self.add(label, value, unit, Provenance.MEASURED, source, **kw)

    def computed(self, label: str, value: Any, unit: str, source: str, **kw: Any) -> Fact:
        """A value derived by the unit-tested domain library."""
        return self.add(label, value, unit, Provenance.COMPUTED, source, **kw)

    def cited(self, label: str, value: Any, unit: str, source: str, **kw: Any) -> Fact:
        """A figure or statement taken from an indexed document."""
        return self.add(label, value, unit, Provenance.CITED, source, **kw)

    # ----------------------------------------------------------- reading --

    def __len__(self) -> int:
        return len(self._facts)

    def __contains__(self, fact_id: object) -> bool:
        return fact_id in self._facts

    def get(self, fact_id: str) -> Fact | None:
        return self._facts.get(fact_id)

    def all(self) -> list[Fact]:
        return [self._facts[k] for k in sorted(self._facts, key=lambda i: int(i[1:]))]

    def by_provenance(self, provenance: Provenance) -> list[Fact]:
        return [f for f in self.all() if f.provenance is provenance]

    def caveats(self) -> list[str]:
        """Every distinct caveat any fact carries, in first-seen order."""
        seen: list[str] = []
        for fact in self.all():
            for caveat in fact.caveats:
                if caveat not in seen:
                    seen.append(caveat)
        return seen

    # ------------------------------------------------------ substitution --

    def substitute(self, text: str) -> tuple[str, list[str]]:
        """Replace ``{{F#}}`` with rendered values.

        Returns the text and the ids of any placeholder that had no fact --
        an unresolved reference is a failure, not something to render as
        literal braces in front of a customer.
        """
        missing: list[str] = []

        def swap(match: re.Match) -> str:
            fact_id = match.group(1)
            fact = self._facts.get(fact_id)
            if fact is None:
                missing.append(fact_id)
                return match.group(0)
            return fact.rendered()

        return PLACEHOLDER_RE.sub(swap, text or ""), missing

    def referenced(self, text: str) -> list[str]:
        return sorted(set(PLACEHOLDER_RE.findall(text or "")), key=lambda i: int(i[1:]))

    @staticmethod
    def bare_numbers(text: str) -> list[str]:
        """Numbers written directly into narrative rather than referenced.

        Run BEFORE substitution. Anything this finds was typed by whoever
        wrote the narrative rather than taken from the ledger, which is the
        one thing the design exists to prevent.
        """
        stripped = _ORDER_RE.sub(" ", text or "")
        stripped = PLACEHOLDER_RE.sub(" ", stripped)
        return [n for n in BARE_NUMBER_RE.findall(stripped) if len(n) > 1]
