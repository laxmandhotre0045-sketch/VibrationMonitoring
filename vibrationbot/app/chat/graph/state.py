"""Graph state and its reducers.

Reducer choice is the classic source of LangGraph bugs, so each one below is
deliberate:

* ``messages`` uses ``add_messages`` — the agent node and ToolNode both append,
  and it handles id-based replacement.
* ``computations`` / ``plots`` / ``trace`` use ``operator.add`` — several nodes
  append across tool-loop iterations, and overwriting would lose earlier
  entries.
* ``retrieved`` / ``graded`` deliberately OVERWRITE. A re-retrieval after a
  query rewrite must *replace* the previous set; appending would re-admit
  exactly the passages the grader just rejected, so the rewrite loop could
  never converge.
* The loop counters are plain ints, incremented as ``state.get(k, 0) + 1``.
  Giving them ``operator.add`` forces every node to return a delta, and one
  node returning the absolute value silently doubles the counter and breaks
  the bound. ``tests/test_graph_state.py`` locks this down.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, Optional, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

Route = Literal["theory", "numeric", "data", "hybrid", "chitchat"]


class GraphState(TypedDict, total=False):
    # --- accumulating channels -------------------------------------------
    messages: Annotated[list[AnyMessage], add_messages]
    computations: Annotated[list[dict[str, Any]], operator.add]
    plots: Annotated[list[dict[str, Any]], operator.add]
    trace: Annotated[list[dict[str, Any]], operator.add]

    # --- request ----------------------------------------------------------
    question: str
    retrieval_query: str
    session_id: str
    doc_ids: Optional[list[str]]
    allowed_docs: list[str]
    top_k: int

    # --- measurement context ---------------------------------------------
    machine_id: Optional[str]
    point_id: Optional[str]
    machine: Optional[dict[str, Any]]
    forcing_freqs: dict[str, dict[str, Any]]
    signal_ids: list[str]
    chart_ids: list[str]
    peaks: list[dict[str, Any]]
    stated_facts: dict[str, Any]

    # --- routing and retrieval (overwrite) --------------------------------
    route: Route
    retrieved: list[dict[str, Any]]
    graded: list[dict[str, Any]]

    # --- output -----------------------------------------------------------
    answer: str
    diagnosis: Optional[dict[str, Any]]
    grounded: bool
    used_fallback: bool
    error: Optional[str]

    # --- bounded loop counters (plain ints, overwrite) --------------------
    rewrite_count: int
    regen_count: int
    tool_loops: int


def bump(state: GraphState, key: str) -> int:
    """Increment a loop counter.

    Always returns the absolute new value, matching the overwrite semantics of
    these keys. Nodes must use this rather than returning a delta.
    """
    return int(state.get(key, 0) or 0) + 1


def new_state(
    question: str,
    session_id: str,
    top_k: int,
    doc_ids: list[str] | None = None,
    machine_id: str | None = None,
    point_id: str | None = None,
    signal_ids: list[str] | None = None,
    chart_ids: list[str] | None = None,
) -> GraphState:
    """Initial state for one turn.

    Counters start explicitly at zero rather than relying on ``.get`` defaults,
    so a checkpoint resumed mid-turn cannot inherit a stale count.
    """
    return GraphState(
        question=question,
        retrieval_query=question,
        session_id=session_id,
        doc_ids=doc_ids,
        allowed_docs=[],
        top_k=top_k,
        machine_id=machine_id,
        point_id=point_id,
        machine=None,
        forcing_freqs={},
        signal_ids=signal_ids or [],
        chart_ids=chart_ids or [],
        peaks=[],
        stated_facts={},
        messages=[],
        computations=[],
        plots=[],
        trace=[],
        retrieved=[],
        graded=[],
        answer="",
        diagnosis=None,
        grounded=True,
        used_fallback=False,
        error=None,
        rewrite_count=0,
        regen_count=0,
        tool_loops=0,
    )
