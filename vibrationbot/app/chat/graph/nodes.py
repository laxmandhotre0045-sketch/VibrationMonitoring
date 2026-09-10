"""Graph node functions.

Every node is a sync ``def`` on purpose. They call genuinely blocking work —
FAISS search, a ~900 ms cross-encoder rerank, numpy FFTs — and LangGraph
dispatches sync nodes to a worker thread during async execution, so the event
loop stays free. Writing them ``async def`` and calling blocking code inside is
the failure mode that freezes health checks under load; routes_documents.py
already documents that trap for the upload path.

Nodes are also individually callable with a plain dict, which is what makes the
offline tests in tests/test_graph_nodes.py possible without compiling a graph
or touching the network.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from pathlib import Path
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from pydantic import BaseModel, Field

from app.domain.machine import machine_store
from app.domain.signatures import SpectralPeak
from app.chat.graph import prompts
from app.chat.graph.state import GraphState, bump
from app.chat.graph.tools_domain import DomainContext, build_domain_tools
from app.chat.graph.tools_platform import build_platform_tools
from app.chat.graph.tools_retrieval import RetrievalContext, build_retrieval_tools
from app.config import (
    AGENT_MAX_ITERATIONS,
    DOCUMENTS_DIR,
    ENABLE_RETRIEVAL_FALLBACK,
    GRAPH_MAX_REGENS,
    GRAPH_MAX_REWRITES,
)
from app.retrieval.index_service import index_service
from app.llm.provider import get_chat_model
from app.llm.openai_utils import openai_error_message, retrieval_only_answer
from app.retrieval.retrieval_service import _retrieval_query_for_turn
from app.chat.sessions import session_service

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Structured output schemas
# --------------------------------------------------------------------------


class RouteDecision(BaseModel):
    route: Literal["theory", "numeric", "data", "hybrid", "chitchat"]
    rewritten_query: str = Field(..., description="Standalone retrieval query")
    machine_id: str | None = None
    point_id: str | None = None
    bearing_designation: str | None = None
    shaft_rpm: float | None = None
    velocity_rms_mm_s: float | None = None
    machine_group: int | None = None
    foundation: Literal["rigid", "flexible"] | None = None
    power_kw: float | None = None
    machine_type: str | None = None
    line_freq_hz: float | None = None


class ExcerptGrade(BaseModel):
    index: int
    relevant: bool
    reason: str = ""


class GradeResult(BaseModel):
    grades: list[ExcerptGrade]


class GroundednessResult(BaseModel):
    grounded: bool
    unsupported_claims: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------

# Per-turn contexts, keyed by session. The tool closures hold mutable state
# that must not be serialised into a checkpoint, so they live outside the graph
# state and are rebuilt each turn.
_TURN_CONTEXTS: dict[str, tuple[RetrievalContext, DomainContext]] = {}


def _contexts(state: GraphState) -> tuple[RetrievalContext, DomainContext]:
    return _TURN_CONTEXTS[state["session_id"]]


def set_turn_contexts(session_id: str, retrieval: RetrievalContext, domain: DomainContext) -> None:
    _TURN_CONTEXTS[session_id] = (retrieval, domain)


def clear_turn_contexts(session_id: str) -> None:
    _TURN_CONTEXTS.pop(session_id, None)


def _trace(node: str, detail: str = "", started: float | None = None) -> list[dict[str, Any]]:
    entry: dict[str, Any] = {"node": node, "detail": detail}
    if started is not None:
        entry["duration_ms"] = int((time.perf_counter() - started) * 1000)
    return [entry]


def _format_history(turns: list) -> str:
    if not turns:
        return "(No prior conversation.)"
    lines: list[str] = []
    for turn in turns[-5:]:
        lines.append(f"User: {turn.question}")
        lines.append(f"Assistant: {turn.answer[:400]}")
    return "\n".join(lines)


def format_excerpts(chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return "(No relevant document excerpts found.)"
    parts: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        pages = chunk.get("page_start", "?")
        page_end = chunk.get("page_end", pages)
        page_str = f"p.{pages}" if pages == page_end else f"pp.{pages}-{page_end}"
        parts.append(
            f"[{i}] ({chunk.get('chunk_type', 'clause')}) "
            f"{chunk.get('section_path', 'Unknown Section')} ({page_str}) "
            f"[{chunk.get('doc_id', '')}]\n{(chunk.get('text') or '').strip()}"
        )
    return "\n\n".join(parts)


def format_computations(computations: list[dict[str, Any]]) -> str:
    """Render computations as the authoritative <COMPUTED> block.

    Inputs and formula are shown so the engineer can redo the arithmetic, and
    the supporting chunk is named so a computed value cites both the tool that
    produced it and the passage that justifies the formula.
    """
    if not computations:
        return "(No calculations were performed this turn.)"
    parts: list[str] = []
    for record in computations:
        cid = record.get("id", "C?")
        inputs = ", ".join(f"{k}={v}" for k, v in (record.get("inputs") or {}).items() if v is not None)
        lines = [f"[{cid}] {record.get('tool', 'tool')} — inputs: {inputs}"]
        lines.append(f"     result: {record.get('summary_text', '') or json.dumps(record.get('outputs', {}))[:600]}")
        if record.get("formula"):
            lines.append(f"     formula: {record['formula']}")
        if record.get("confidence", 1.0) < 1.0:
            lines.append(f"     confidence: {record['confidence']:.2f} — see assumptions")
        for assumption in record.get("assumptions", []) or []:
            lines.append(f"     assumption: {assumption}")
        if record.get("supporting_chunk_id"):
            lines.append(
                f"     grounded by: {record['supporting_doc_id']}#{record['supporting_chunk_id']}"
            )
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def _format_machine(state: GraphState) -> str:
    machine = state.get("machine")
    if not machine:
        return "(No machine profile registered for this conversation.)"
    freqs = state.get("forcing_freqs") or {}
    lines = [
        f"Machine {machine.get('machine_id')} — {machine.get('name', '')} "
        f"[{machine.get('type', 'unknown')}], {machine.get('foundation', '?')} foundation"
    ]
    if freqs:
        lines.append("Forcing frequencies:")
        for freq in sorted(freqs.values(), key=lambda f: f["order"]):
            flag = "" if freq.get("confidence", 1.0) >= 1.0 else " (estimated)"
            lines.append(f"  {freq['label']}: {freq['hz']:.2f} Hz ({freq['order']:.3f}x){flag}")
    return "\n".join(lines)


def _image_data_url(path: Path) -> str | None:
    if not path.exists():
        return None
    mime = "png" if path.suffix.lower() == ".png" else "jpeg"
    return f"data:image/{mime};base64,{base64.standard_b64encode(path.read_bytes()).decode('ascii')}"


# --------------------------------------------------------------------------
# Nodes
# --------------------------------------------------------------------------


def prepare(state: GraphState) -> dict[str, Any]:
    """Resolve session, available documents, and the retrieval query.

    Raises the same exception types the legacy services raise, so the existing
    handlers in routes_chat.py keep mapping them to 404 and 400.
    """
    started = time.perf_counter()
    session_id = state["session_id"]

    ready = index_service.list_ready_doc_ids()
    requested = state.get("doc_ids")
    allowed = [d for d in (requested or ready) if d in ready]
    if requested and not allowed:
        raise ValueError("None of the requested doc_ids are indexed and ready.")

    last_question = session_service.get_last_question(session_id)
    retrieval_query = _retrieval_query_for_turn(state["question"], last_question)

    return {
        "allowed_docs": allowed,
        "retrieval_query": retrieval_query,
        "trace": _trace("prepare", f"{len(allowed)} documents available", started),
    }


def classify(state: GraphState) -> dict[str, Any]:
    """Route the question and extract stated machine facts in one call.

    Merged deliberately: a separate query-rewrite node would double latency on
    every turn for no measurable gain, since both tasks read the same context.
    """
    started = time.perf_counter()
    history = _format_history(session_service.get_history(state["session_id"]))

    try:
        model = get_chat_model("classify").with_structured_output(RouteDecision)
        decision: RouteDecision = model.invoke(
            prompts.CLASSIFY_PROMPT.format(history=history, question=state["question"])
        )
    except Exception as exc:  # noqa: BLE001 — routing must never fail the turn
        logger.warning("Classification failed, defaulting to hybrid: %s", exc)
        return {
            "route": "hybrid",
            "trace": _trace("classify", f"failed, defaulted to hybrid: {exc}", started),
        }

    stated = {
        k: v
        for k, v in {
            "bearing_designation": decision.bearing_designation,
            "shaft_rpm": decision.shaft_rpm,
            "velocity_rms_mm_s": decision.velocity_rms_mm_s,
            "machine_group": decision.machine_group,
            "foundation": decision.foundation,
            "power_kw": decision.power_kw,
            "machine_type": decision.machine_type,
            "line_freq_hz": decision.line_freq_hz,
        }.items()
        if v is not None
    }

    # A machine_id supplied on the request is authoritative over one the model
    # thought it saw in the text.
    machine_id = state.get("machine_id") or decision.machine_id

    return {
        "route": decision.route,
        "retrieval_query": decision.rewritten_query or state["retrieval_query"],
        "machine_id": machine_id,
        "point_id": state.get("point_id") or decision.point_id,
        "stated_facts": stated,
        "trace": _trace("classify", f"route={decision.route}", started),
    }


def resolve_machine_context(state: GraphState) -> dict[str, Any]:
    """Load the machine profile and precompute its forcing frequencies.

    Anything the user stated this turn wins over the stored nameplate — an
    explicitly given RPM is a measurement, the profile's is a specification.
    """
    started = time.perf_counter()
    machine_id = state.get("machine_id")
    _, domain_ctx = _contexts(state)
    domain_ctx.stated = state.get("stated_facts") or {}

    if not machine_id:
        return {"trace": _trace("resolve_machine_context", "no machine_id", started)}

    try:
        profile = machine_store.load(machine_id)
    except ValueError as exc:
        return {"trace": _trace("resolve_machine_context", f"invalid machine_id: {exc}", started)}

    if profile is None:
        return {"trace": _trace("resolve_machine_context", f"{machine_id} not registered", started)}

    from app.domain.machine import derived_frequencies

    domain_ctx.profile = profile
    domain_ctx.point_id = state.get("point_id")
    freqs = derived_frequencies(profile, state.get("point_id"), domain_ctx.shaft_rpm)

    return {
        "machine": profile.model_dump(),
        "forcing_freqs": {k: f.as_dict() for k, f in freqs.items()},
        "trace": _trace(
            "resolve_machine_context", f"{machine_id}, {len(freqs)} forcing frequencies", started
        ),
    }


def retrieve(state: GraphState) -> dict[str, Any]:
    """Retrieve document excerpts. Overwrites, never appends — see state.py."""
    started = time.perf_counter()
    retrieval_ctx, _ = _contexts(state)
    results = retrieval_ctx.search(state["retrieval_query"], top_k=state["top_k"])
    return {
        "retrieved": results,
        "trace": _trace("retrieve", f"{len(results)} excerpts", started),
    }


def grade(state: GraphState) -> dict[str, Any]:
    """Grade all retrieved excerpts for relevance in ONE batched call.

    One call per excerpt would cost top_k times as much for a binary decision.
    """
    started = time.perf_counter()
    retrieved = state.get("retrieved") or []
    if not retrieved:
        return {"graded": [], "trace": _trace("grade", "nothing retrieved", started)}

    listing = "\n\n".join(
        f"[{i}] {(chunk.get('text') or '')[:500]}" for i, chunk in enumerate(retrieved, start=1)
    )
    try:
        model = get_chat_model("grade").with_structured_output(GradeResult)
        result: GradeResult = model.invoke(
            prompts.GRADE_PROMPT.format(question=state["question"], excerpts=listing)
        )
        keep_indexes = {g.index for g in result.grades if g.relevant}
        reasons = [g.reason for g in result.grades if not g.relevant and g.reason]
        graded = [chunk for i, chunk in enumerate(retrieved, start=1) if i in keep_indexes]
    except Exception as exc:  # noqa: BLE001 — degrade to ungraded retrieval
        logger.warning("Grading failed, keeping all excerpts: %s", exc)
        return {
            "graded": retrieved,
            "trace": _trace("grade", f"failed, kept all: {exc}", started),
        }

    return {
        "graded": graded,
        "stated_facts": {**(state.get("stated_facts") or {}), "_grade_reasons": reasons[:3]},
        "trace": _trace("grade", f"{len(graded)}/{len(retrieved)} relevant", started),
    }


def rewrite(state: GraphState) -> dict[str, Any]:
    """Reformulate the search query after a weak retrieval. Bounded by GRAPH_MAX_REWRITES."""
    started = time.perf_counter()
    reasons = (state.get("stated_facts") or {}).get("_grade_reasons") or []

    try:
        model = get_chat_model("classify")
        response = model.invoke(
            prompts.REWRITE_PROMPT.format(
                question=state["question"],
                previous_query=state["retrieval_query"],
                reasons="; ".join(reasons) or "no relevant passages were returned",
            )
        )
        new_query = (getattr(response, "content", "") or "").strip() or state["retrieval_query"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Rewrite failed, reusing previous query: %s", exc)
        new_query = state["retrieval_query"]

    return {
        "retrieval_query": new_query,
        "rewrite_count": bump(state, "rewrite_count"),
        "trace": _trace("rewrite", f"-> {new_query[:80]}", started),
    }


def agent(state: GraphState) -> dict[str, Any]:
    """Let the model call domain and retrieval tools until it has what it needs."""
    started = time.perf_counter()
    retrieval_ctx, domain_ctx = _contexts(state)
    tools = build_domain_tools(domain_ctx) + build_retrieval_tools(retrieval_ctx) + build_platform_tools()

    messages = list(state.get("messages") or [])
    if not messages:
        context_note = _format_machine(state)
        excerpts = format_excerpts(state.get("graded") or state.get("retrieved") or [])
        messages = [
            SystemMessage(content=prompts.SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Question: {state['question']}\n\n"
                    f"<MACHINE>\n{context_note}\n</MACHINE>\n\n"
                    f"<EXCERPTS_SO_FAR>\n{excerpts}\n</EXCERPTS_SO_FAR>\n\n"
                    "Call the tools you need, then stop. Do not write the final answer yet."
                )
            ),
        ]

    try:
        response = get_chat_model("agent").bind_tools(tools).invoke(messages)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Agent call failed: %s", exc)
        return {
            "error": openai_error_message(exc) or str(exc),
            "trace": _trace("agent", f"failed: {exc}", started),
        }

    return {
        "messages": messages[len(state.get("messages") or []) :] + [response],
        "trace": _trace("agent", f"{len(getattr(response, 'tool_calls', []) or [])} tool calls", started),
    }


def execute_tools(state: GraphState) -> dict[str, Any]:
    """Run the requested tools and collect their artifacts.

    Domain tools return ``(summary, record)``; the summary goes into the tool
    message the model reads, and the record goes into ``computations``, which
    the model never sees.
    """
    started = time.perf_counter()
    retrieval_ctx, domain_ctx = _contexts(state)
    tools = {t.name: t for t in build_domain_tools(domain_ctx) + build_retrieval_tools(retrieval_ctx) + build_platform_tools()}

    last = (state.get("messages") or [])[-1]
    tool_calls = getattr(last, "tool_calls", None) or []
    messages: list[Any] = []
    computations: list[dict[str, Any]] = []
    existing = len(state.get("computations") or [])

    for call in tool_calls:
        name = call.get("name", "")
        tool = tools.get(name)
        if tool is None:
            messages.append(ToolMessage(content=f"Unknown tool: {name}", tool_call_id=call["id"]))
            continue
        try:
            result = tool.invoke(call)
        except Exception as exc:  # noqa: BLE001 — a bad tool call must not kill the turn
            logger.warning("Tool %s failed: %s", name, exc)
            messages.append(
                ToolMessage(content=f"Tool {name} failed: {exc}", tool_call_id=call["id"])
            )
            continue

        messages.append(result)
        artifact = getattr(result, "artifact", None)
        if isinstance(artifact, dict):
            record = dict(artifact)
            record["id"] = f"C{existing + len(computations) + 1}"
            record["summary_text"] = (result.content or "")[:800]
            computations.append(record)

    return {
        "messages": messages,
        "computations": computations,
        "tool_loops": bump(state, "tool_loops"),
        "trace": _trace("execute_tools", f"{len(tool_calls)} calls, {len(computations)} records", started),
    }


def ground_computations(state: GraphState) -> dict[str, Any]:
    """Attach a supporting passage to each computation.

    This is what turns "BPFO = 104.56 Hz" into a claim with a citation: the
    formula's own query hint retrieves the passage that defines it.
    """
    started = time.perf_counter()
    computations = state.get("computations") or []
    ungrounded = [c for c in computations if not c.get("supporting_chunk_id")]
    if not ungrounded:
        return {"trace": _trace("ground_computations", "nothing to ground", started)}

    retrieval_ctx, _ = _contexts(state)
    # One retrieval per distinct hint, not per computation — several bearing
    # calculations share the same formula and therefore the same passage.
    by_hint: dict[str, list[dict[str, Any]]] = {}
    for record in ungrounded:
        hint = ((record.get("formula_source") or {}).get("query_hint") or "").strip()
        if hint:
            by_hint.setdefault(hint, []).append(record)

    grounded = 0
    for hint, records in by_hint.items():
        try:
            results = retrieval_ctx.search(hint, top_k=2)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Grounding retrieval failed for %r: %s", hint[:40], exc)
            continue
        if not results:
            continue
        best = results[0]
        for record in records:
            record["supporting_chunk_id"] = best.get("chunk_id")
            record["supporting_doc_id"] = best.get("doc_id")
            grounded += 1

    # computations uses operator.add, so returning the list would duplicate it.
    # The records were mutated in place; report progress via trace only.
    return {"trace": _trace("ground_computations", f"grounded {grounded}", started)}


def generate(state: GraphState) -> dict[str, Any]:
    """Write the answer from computed results plus retrieved excerpts."""
    started = time.perf_counter()

    if state.get("route") == "chitchat":
        try:
            response = get_chat_model("generate").invoke(
                prompts.CHITCHAT_PROMPT.format(question=state["question"])
            )
            return {
                "answer": (getattr(response, "content", "") or "").strip(),
                "trace": _trace("generate", "chitchat", started),
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("Chitchat generation failed: %s", exc)
            return {
                "answer": "I'm a vibration analysis assistant — ask me about bearing fault "
                "frequencies, ISO severity limits, or a measurement you'd like interpreted.",
                "trace": _trace("generate", f"chitchat fallback: {exc}", started),
            }

    retrieval_ctx, _ = _contexts(state)
    chunks = state.get("graded") or state.get("retrieved") or []
    if not chunks and retrieval_ctx.collected:
        chunks = retrieval_ctx.best(state["top_k"])

    computed = format_computations(state.get("computations") or [])
    excerpts = format_excerpts(chunks)
    history = _format_history(session_service.get_history(state["session_id"]))

    prompt = prompts.GENERATE_PROMPT.format(
        computed=computed,
        excerpts=excerpts,
        machine=_format_machine(state),
        history=history,
        question=state["question"],
    )
    if state.get("regen_count"):
        unsupported = (state.get("stated_facts") or {}).get("_unsupported") or []
        prompt += prompts.REGENERATE_SUFFIX.format(unsupported="; ".join(unsupported))

    try:
        response = get_chat_model("generate").invoke(
            [SystemMessage(content=prompts.SYSTEM_PROMPT), HumanMessage(content=prompt)]
        )
        answer = (getattr(response, "content", "") or "").strip()
    except Exception as exc:  # noqa: BLE001
        if ENABLE_RETRIEVAL_FALLBACK and openai_error_message(exc):
            logger.warning("Generation failed — falling back to retrieval-only answer")
            return {
                "answer": retrieval_only_answer(state["question"], chunks),
                "used_fallback": True,
                "trace": _trace("generate", f"fallback: {exc}", started),
            }
        raise

    return {
        "answer": answer,
        "retrieved": chunks,
        "trace": _trace("generate", f"{len(answer)} chars", started),
    }


def vision_answer(state: GraphState) -> dict[str, Any]:
    """Refine the answer with the actual figure images attached.

    A refinement pass, not a second answer from scratch: ``generate`` already
    produced grounded text, and this adds what only the pixels can show.
    """
    started = time.perf_counter()
    chunks = state.get("graded") or state.get("retrieved") or []
    figures = [c for c in chunks if c.get("chunk_type") in ("image", "diagram")]

    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                f"Question: {state['question']}\n\n"
                f"Draft answer:\n{state.get('answer', '')}\n\n"
                "The figures referenced above are attached. Correct or sharpen the draft using "
                "what the images actually show — axis labels, units, trends, values. Keep every "
                "computed number exactly as it is. Return the improved answer only."
            ),
        }
    ]
    attached = 0
    for chunk in figures:
        asset_path = chunk.get("asset_path", "")
        if not asset_path:
            continue
        data_url = _image_data_url(DOCUMENTS_DIR / chunk["doc_id"] / asset_path)
        if data_url:
            content.append({"type": "image_url", "image_url": {"url": data_url}})
            attached += 1

    for plot in state.get("plots") or []:
        path = plot.get("path")
        if path:
            data_url = _image_data_url(Path(path))
            if data_url:
                content.append({"type": "image_url", "image_url": {"url": data_url}})
                attached += 1

    if attached == 0:
        return {"trace": _trace("vision_answer", "no images resolved", started)}

    try:
        response = get_chat_model("vision").invoke([HumanMessage(content=content)])
        refined = (getattr(response, "content", "") or "").strip()
    except Exception as exc:  # noqa: BLE001 — keep the draft on failure
        logger.warning("Vision refinement failed, keeping draft: %s", exc)
        return {"trace": _trace("vision_answer", f"failed: {exc}", started)}

    return {
        "answer": refined or state.get("answer", ""),
        "trace": _trace("vision_answer", f"{attached} images", started),
    }


def check_groundedness(state: GraphState) -> dict[str, Any]:
    """Verify every claim traces to a computation or an excerpt."""
    started = time.perf_counter()
    if state.get("route") == "chitchat" or state.get("used_fallback"):
        return {"grounded": True, "trace": _trace("check_groundedness", "skipped", started)}

    chunks = state.get("graded") or state.get("retrieved") or []
    try:
        model = get_chat_model("verify").with_structured_output(GroundednessResult)
        result: GroundednessResult = model.invoke(
            prompts.GROUNDEDNESS_PROMPT.format(
                computed=format_computations(state.get("computations") or []),
                excerpts=format_excerpts(chunks),
                answer=state.get("answer", ""),
            )
        )
    except Exception as exc:  # noqa: BLE001 — never block an answer on the checker
        logger.warning("Groundedness check failed, passing through: %s", exc)
        return {"grounded": True, "trace": _trace("check_groundedness", f"failed: {exc}", started)}

    if result.grounded:
        return {"grounded": True, "trace": _trace("check_groundedness", "grounded", started)}

    return {
        "grounded": False,
        "regen_count": bump(state, "regen_count"),
        "stated_facts": {
            **(state.get("stated_facts") or {}),
            "_unsupported": result.unsupported_claims,
        },
        "trace": _trace(
            "check_groundedness", f"{len(result.unsupported_claims)} unsupported", started
        ),
    }


def finalize(state: GraphState) -> dict[str, Any]:
    """Persist the turn to session history."""
    started = time.perf_counter()
    session_service.add_turn(state["session_id"], state["question"], state.get("answer", ""))
    return {"trace": _trace("finalize", "", started)}


# --------------------------------------------------------------------------
# Conditional edges
# --------------------------------------------------------------------------


def route_after_classify(state: GraphState) -> str:
    route = state.get("route", "hybrid")
    if route == "chitchat":
        return "generate"
    if route == "theory":
        return "retrieve"
    return "resolve_machine_context"


def route_after_grade(state: GraphState) -> str:
    """Retry retrieval once with a better query if too little was relevant.

    Bounded at GRAPH_MAX_REWRITES: a second failure proceeds with whatever was
    found rather than looping.
    """
    graded = state.get("graded") or []
    retrieved = state.get("retrieved") or []
    threshold = max(1, len(retrieved) // 3)
    if len(graded) < threshold and state.get("rewrite_count", 0) < GRAPH_MAX_REWRITES:
        return "rewrite"
    return "agent"


def route_after_agent(state: GraphState) -> str:
    if state.get("error"):
        return "generate"
    last = (state.get("messages") or [])[-1] if state.get("messages") else None
    has_tool_calls = bool(getattr(last, "tool_calls", None))
    if has_tool_calls and state.get("tool_loops", 0) < AGENT_MAX_ITERATIONS:
        return "execute_tools"
    return "ground_computations"


def route_after_tools(state: GraphState) -> str:
    if state.get("tool_loops", 0) >= AGENT_MAX_ITERATIONS:
        return "ground_computations"
    return "agent"


def route_after_generate(state: GraphState) -> str:
    chunks = state.get("graded") or state.get("retrieved") or []
    has_figures = any(c.get("chunk_type") in ("image", "diagram") for c in chunks)
    if has_figures or state.get("plots"):
        return "vision_answer"
    return "check_groundedness"


def route_after_groundedness(state: GraphState) -> str:
    if not state.get("grounded", True) and state.get("regen_count", 0) <= GRAPH_MAX_REGENS:
        return "generate"
    return "finalize"
