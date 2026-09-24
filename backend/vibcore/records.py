"""ComputationRecord — the audit trail for every number the bot states.

A computed value is only trustworthy if the user can see where it came from, so
every domain tool returns two things: a short human-readable summary (which is
what the LLM sees) and one of these records (which the LLM never sees, and
therefore cannot paraphrase or corrupt). The record carries the inputs, the
formula, the assumptions, and a hint for retrieving the passage that justifies
the formula.

That last part is what turns "BPFO = 104.56 Hz" from an assertion into a
citation: the graph fills ``supporting_chunk`` by retrieving on
``formula_source.query_hint``, so the answer can point at both the tool that
computed it and the textbook that defines it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

SourceKind = Literal["textbook", "standard", "definition", "measurement"]


@dataclass(frozen=True)
class FormulaSource:
    """Where the formula behind a computation comes from.

    ``query_hint`` is a retrieval query, not a citation. The graph runs it
    against the indexed corpus to find the passage that actually explains the
    formula, so the hint should read like something a textbook section would
    match — "ball pass frequency outer race derivation", not "BPFO".
    """

    kind: SourceKind = "definition"
    ref: str = ""
    query_hint: str = ""


@dataclass
class ComputationRecord:
    """One deterministic computation, with everything needed to redo it by hand."""

    tool: str
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    formula: str = ""
    formula_source: FormulaSource = field(default_factory=FormulaSource)
    assumptions: list[str] = field(default_factory=list)
    # 1.0 = exact given the inputs (catalog geometry, tabulated standard).
    # Lower values flag estimated geometry, VLM-read chart values, and anything
    # else the user should be told about rather than quietly trust.
    confidence: float = 1.0
    # Assigned by the graph as C1, C2, ... so the answer can cite [C1].
    id: str = ""
    # Filled in by the ground_computations node.
    supporting_chunk_id: str | None = None
    supporting_doc_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def summarize_assumptions(records: list[ComputationRecord]) -> list[str]:
    """Distinct assumptions across records, in first-seen order.

    The generation prompt is required to surface these, so duplicates across
    several computations would produce a repetitive "Assumptions" block.
    """
    seen: set[str] = set()
    out: list[str] = []
    for record in records:
        for assumption in record.assumptions:
            if assumption not in seen:
                seen.add(assumption)
                out.append(assumption)
    return out
