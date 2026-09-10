from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ChatRequest, ChatResponse
from app.chat.agent_rag_service import agent_answer
from app.chat.graph_rag_service import graph_answer
from app.chat.rag_service import rag_answer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

# graph  — LangGraph vibration analyst: routing, domain tools, self-correction
# agent  — legacy hand-rolled OpenAI tool loop
# simple — single-shot retrieval + answer
MODES = {"simple": rag_answer, "agent": agent_answer, "graph": graph_answer}
DEFAULT_MODE = "graph"


@router.post("", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    mode: str = Query(DEFAULT_MODE, description="graph, agent, or simple"),
):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    answer_fn = MODES.get(mode)
    if answer_fn is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown mode {mode!r}. Use one of: {', '.join(sorted(MODES))}.",
        )

    kwargs = {
        "question": request.question.strip(),
        "session_id": request.session_id,
        "doc_ids": request.doc_ids,
        "top_k": request.top_k,
    }
    if answer_fn is graph_answer:
        kwargs.update(
            machine_id=request.machine_id,
            point_id=request.point_id,
            signal_ids=request.signal_ids,
            chart_ids=request.chart_ids,
        )

    try:
        return answer_fn(**kwargs)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RecursionError as exc:
        # GraphRecursionError subclasses RecursionError. graph_answer normally
        # handles it and degrades gracefully; this catches any that escape so
        # a reasoning-budget overrun never surfaces as an opaque 500.
        logger.warning("Graph recursion limit escaped to the route handler: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="The assistant hit its reasoning budget on this question. "
            "Try narrowing it, or supplying the missing input.",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chat failed: {exc}") from exc


@router.post("/simple", response_model=ChatResponse)
def chat_simple(request: ChatRequest):
    return chat(request, mode="simple")


@router.post("/agent", response_model=ChatResponse)
def chat_agent(request: ChatRequest):
    return chat(request, mode="agent")
