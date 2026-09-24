"""StateGraph wiring and the compiled singletons.

The checkpointer is a SqliteSaver keyed by ``thread_id == session_id``, which
is what gives graph mode conversation memory that survives a restart — the
in-memory SessionService does not. Both are written to; see
graph_rag_service.py for why SessionService is bridged rather than replaced.
"""

from __future__ import annotations

import logging
import sqlite3
import threading

from langgraph.graph import END, START, StateGraph

from app.chat.graph import nodes
from app.chat.graph.state import GraphState
from app.config import AGENT_MAX_ITERATIONS, DATA_DIR, GRAPH_CHECKPOINT_PATH

logger = logging.getLogger(__name__)

# Enough headroom for the worst legitimate path — full tool loop, one rewrite,
# one regeneration — without letting a cycle run away.
RECURSION_LIMIT = 2 * AGENT_MAX_ITERATIONS + 16

_lock = threading.Lock()
_graph = None
_saver = None


def build_graph() -> StateGraph:
    """Wire the node graph. Compiled separately so tests can supply their own checkpointer."""
    builder = StateGraph(GraphState)

    builder.add_node("prepare", nodes.prepare)
    builder.add_node("classify", nodes.classify)
    builder.add_node("resolve_machine_context", nodes.resolve_machine_context)
    builder.add_node("retrieve", nodes.retrieve)
    builder.add_node("grade", nodes.grade)
    builder.add_node("rewrite", nodes.rewrite)
    builder.add_node("agent", nodes.agent)
    builder.add_node("execute_tools", nodes.execute_tools)
    builder.add_node("ground_computations", nodes.ground_computations)
    builder.add_node("generate", nodes.generate)
    builder.add_node("vision_answer", nodes.vision_answer)
    builder.add_node("check_groundedness", nodes.check_groundedness)
    builder.add_node("finalize", nodes.finalize)

    builder.add_edge(START, "prepare")
    builder.add_edge("prepare", "classify")

    # chitchat short-circuits straight to generate — that is what stops "hi"
    # costing an embedding pass and a ~900 ms rerank.
    builder.add_conditional_edges(
        "classify",
        nodes.route_after_classify,
        {"generate": "generate", "retrieve": "retrieve", "resolve_machine_context": "resolve_machine_context"},
    )

    # Measurement routes still retrieve, but only after machine context is
    # resolved, so the query can use the machine's own terminology.
    builder.add_edge("resolve_machine_context", "retrieve")
    builder.add_edge("retrieve", "grade")
    builder.add_conditional_edges(
        "grade", nodes.route_after_grade, {"rewrite": "rewrite", "agent": "agent"}
    )
    builder.add_edge("rewrite", "retrieve")

    builder.add_conditional_edges(
        "agent",
        nodes.route_after_agent,
        {"execute_tools": "execute_tools", "ground_computations": "ground_computations", "generate": "generate"},
    )
    builder.add_conditional_edges(
        "execute_tools",
        nodes.route_after_tools,
        {"agent": "agent", "ground_computations": "ground_computations"},
    )
    builder.add_edge("ground_computations", "generate")

    builder.add_conditional_edges(
        "generate",
        nodes.route_after_generate,
        {"vision_answer": "vision_answer", "check_groundedness": "check_groundedness"},
    )
    builder.add_edge("vision_answer", "check_groundedness")
    builder.add_conditional_edges(
        "check_groundedness",
        nodes.route_after_groundedness,
        {"generate": "generate", "finalize": "finalize"},
    )
    builder.add_edge("finalize", END)

    return builder


def _make_saver():
    """SqliteSaver over a long-lived connection.

    ``check_same_thread=False`` is required because FastAPI runs the sync chat
    handler in a threadpool, so the connection is used from several threads.
    ``SqliteSaver.from_conn_string`` is deliberately not used: it is a context
    manager, and calling it bare closes the connection immediately.
    """
    from langgraph.checkpoint.sqlite import SqliteSaver

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(GRAPH_CHECKPOINT_PATH), check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return saver


def get_graph():
    """Compiled graph singleton, built on first use."""
    global _graph, _saver
    if _graph is None:
        with _lock:
            if _graph is None:
                try:
                    _saver = _make_saver()
                except Exception as exc:  # noqa: BLE001 — memory beats no service
                    logger.warning(
                        "SQLite checkpointer unavailable (%s); graph memory will not "
                        "survive a restart this session.",
                        exc,
                    )
                    from langgraph.checkpoint.memory import MemorySaver

                    _saver = MemorySaver()
                _graph = build_graph().compile(checkpointer=_saver)
                logger.info("LangGraph compiled with %s", type(_saver).__name__)
    return _graph


def is_ready() -> bool:
    return _graph is not None
