"""graph_answer — the mode=graph entry point.

Same signature as ``agent_answer`` and ``rag_answer``, so routes_chat.py picks
between them with a dict lookup and the legacy modes keep working untouched.

SessionService is bridged rather than replaced. It still backs
``_retrieval_query_for_turn``'s follow-up detection and the legacy modes, and
keeping both written means a user switching mode mid-conversation does not lose
history. The asymmetry is real and worth knowing: graph-mode history also lives
in the SQLite checkpoint and survives a restart, whereas agent/simple history
does not.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.domain.signatures import SpectralPeak
from app.chat.graph import nodes as graph_nodes
from app.chat.graph.build import RECURSION_LIMIT, get_graph
from app.chat.graph.state import new_state
from app.chat.graph.tools_domain import DomainContext
from app.chat.graph.tools_retrieval import RetrievalContext
from app.config import DEFAULT_TOP_K, INTERACTION_LOG_PATH, OPENAI_API_KEY
from app.schemas import ChatResponse, ComputationRecordOut, PlotRef, SourceCitation, TraceStep
from app.retrieval.index_service import index_service
from app.chat.sessions import session_service

logger = logging.getLogger(__name__)


def _asset_url(doc_id: str, asset_path: str) -> str | None:
    if not asset_path:
        return None
    return f"/api/v1/documents/{doc_id}/assets/{Path(asset_path).name}"


def _to_sources(chunks: list[dict[str, Any]]) -> list[SourceCitation]:
    return [
        SourceCitation(
            chunk_id=c.get("chunk_id", ""),
            text=(c.get("text") or "")[:300] + ("..." if len(c.get("text") or "") > 300 else ""),
            section_path=c.get("section_path", ""),
            page_start=int(c.get("page_start", 0)),
            page_end=int(c.get("page_end", 0)),
            score=float(c.get("score", 0.0)),
            doc_id=c.get("doc_id", ""),
            chunk_type=c.get("chunk_type", "clause"),
            asset_url=_asset_url(c.get("doc_id", ""), c.get("asset_path", "")),
        )
        for c in chunks
    ]


def _to_computations(records: list[dict[str, Any]]) -> list[ComputationRecordOut]:
    """Computations travel in their own list, never in ``sources``.

    SourceCitation requires integer page numbers, so a computation folded into
    it would render as "pp.0-0" in the existing UI.
    """
    out: list[ComputationRecordOut] = []
    for record in records:
        out.append(
            ComputationRecordOut(
                id=record.get("id", ""),
                tool=record.get("tool", ""),
                inputs={k: v for k, v in (record.get("inputs") or {}).items() if v is not None},
                outputs=record.get("outputs") or {},
                summary=record.get("summary_text", ""),
                formula=record.get("formula", ""),
                assumptions=record.get("assumptions") or [],
                confidence=float(record.get("confidence", 1.0)),
                supporting_chunk_id=record.get("supporting_chunk_id"),
                supporting_doc_id=record.get("supporting_doc_id"),
            )
        )
    return out


def _log_interaction(payload: dict[str, Any]) -> None:
    try:
        INTERACTION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with INTERACTION_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {**payload, "timestamp": datetime.now(timezone.utc).isoformat()},
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception as exc:  # noqa: BLE001 — logging must never break a reply
        logger.warning("Could not write interaction log: %s", exc)


def graph_answer(
    question: str,
    session_id: str | None = None,
    doc_ids: list[str] | None = None,
    top_k: int = DEFAULT_TOP_K,
    machine_id: str | None = None,
    point_id: str | None = None,
    signal_ids: list[str] | None = None,
    chart_ids: list[str] | None = None,
    peaks: list[SpectralPeak] | None = None,
) -> ChatResponse:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set")

    ready = index_service.list_ready_doc_ids()
    if not ready and not machine_id:
        raise FileNotFoundError(
            "No indexed documents available. Upload a PDF or Word document first, "
            "or register a machine to use the calculation tools."
        )

    sid = session_service.get_or_create(session_id)
    allowed = [d for d in (doc_ids or ready) if d in ready]

    retrieval_ctx = RetrievalContext(allowed_docs=allowed, top_k=top_k)
    domain_ctx = DomainContext(point_id=point_id, peaks=peaks or [])
    graph_nodes.set_turn_contexts(sid, retrieval_ctx, domain_ctx)

    state = new_state(
        question=question,
        session_id=sid,
        top_k=top_k,
        doc_ids=doc_ids,
        machine_id=machine_id,
        point_id=point_id,
        signal_ids=signal_ids,
        chart_ids=chart_ids,
    )

    try:
        final = get_graph().invoke(
            state,
            config={"configurable": {"thread_id": sid}, "recursion_limit": RECURSION_LIMIT},
        )
    except RecursionError:
        # GraphRecursionError subclasses RecursionError. Degrading to whatever
        # was retrieved beats a 500 — the user still gets the excerpts.
        logger.warning("Graph hit its recursion limit for session %s", sid)
        chunks = retrieval_ctx.best(top_k)
        answer = (
            "I reached my reasoning budget on this question before settling on an answer. "
            "Here is what I found — try narrowing the question, or supply the missing "
            "input (running speed, bearing designation, or the measurement itself)."
        )
        session_service.add_turn(sid, question, answer)
        return ChatResponse(
            answer=answer, sources=_to_sources(chunks), session_id=sid, route="budget_exhausted"
        )
    finally:
        graph_nodes.clear_turn_contexts(sid)

    chunks = final.get("graded") or final.get("retrieved") or retrieval_ctx.best(top_k)
    computations = final.get("computations") or []

    _log_interaction(
        {
            "session_id": sid,
            "mode": "graph",
            "question": question,
            "route": final.get("route"),
            "machine_id": machine_id,
            "doc_ids": allowed,
            "tool_calls": domain_ctx.calls + retrieval_ctx.calls,
            "computation_count": len(computations),
            "source_count": len(chunks),
            "grounded": final.get("grounded", True),
            "retrieval_fallback": final.get("used_fallback", False),
            "answer_preview": (final.get("answer") or "")[:200],
        }
    )

    return ChatResponse(
        answer=final.get("answer", ""),
        sources=_to_sources(chunks),
        session_id=sid,
        route=final.get("route"),
        computations=_to_computations(computations),
        plots=[PlotRef(**p) for p in (final.get("plots") or [])],
        grounded=final.get("grounded", True),
        trace=[TraceStep(**t) for t in (final.get("trace") or [])],
    )
