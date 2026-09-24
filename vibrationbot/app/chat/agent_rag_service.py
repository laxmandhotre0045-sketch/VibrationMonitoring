from __future__ import annotations

import base64
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import (
    AGENT_MAX_ITERATIONS,
    AGENT_SKIP_FINAL_CALL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_K,
    DOCUMENTS_DIR,
    ENABLE_RETRIEVAL_FALLBACK,
    INTERACTION_LOG_PATH,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    VISION_MODEL,
)
from app.schemas import ChatResponse, SourceCitation
from app.retrieval.chunks import get_chunk_by_id
from app.retrieval.index_service import index_service
from app.llm.openai_utils import (
    make_openai_client,
    openai_error_message,
    raise_openai_error,
    retrieval_only_answer,
)
from app.retrieval.retrieval_service import (
    _is_follow_up,
    _retrieval_query_for_turn,
    retrieve_across_documents,
)
from app.chat.sessions import session_service

logger = logging.getLogger(__name__)

AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "semantic_search",
            "description": "Search document excerpts by semantic meaning. Use for general questions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "top_k": {"type": "integer", "description": "Number of results", "default": 6},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "table_search",
            "description": "Search specifically in table chunks. Use when the question involves tabular data, rows, columns, or values.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Table-focused search query"},
                    "top_k": {"type": "integer", "description": "Number of results", "default": 4},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_figure",
            "description": "Load a figure/chart/image chunk by chunk_id for visual analysis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "chunk_id": {"type": "string", "description": "Chunk ID of the figure"},
                    "doc_id": {"type": "string", "description": "Document ID containing the figure"},
                },
                "required": ["chunk_id", "doc_id"],
            },
        },
    },
]

SYSTEM_PROMPT = """You are an agentic document assistant with access to search tools over uploaded PDF and Word documents.
Use tools to gather relevant excerpts before answering. For questions about charts, graphs, or figures, use table_search or get_figure as needed.

When you have gathered enough context, write the final answer directly (do not call any more tools) following these rules:
- Answer ONLY from the retrieved excerpts. Do not use outside knowledge.
- If the answer is not in the excerpts, respond exactly: "I do not know from the provided document excerpts."
- One brief summary sentence, then bullet points. Cite document sections and page numbers.
- Do not use markdown headings (no # or ##). Do not repeat the same bullet twice."""

FINAL_ANSWER_PROMPT = """Answer the user's question using ONLY the retrieved context below.
Rules:
- Answer only from the context. Do not use outside knowledge.
- If not found, respond: "I do not know from the provided document excerpts."
- One brief summary sentence, then bullet points.
- No markdown headings.

<CONTEXT>
{context}
</CONTEXT>

<CONVERSATION_HISTORY>
{history}
</CONVERSATION_HISTORY>

Question: {question}

Answer:"""


def _format_context(chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return "(No relevant document excerpts found.)"
    parts: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        section = chunk.get("section_path", "Unknown Section")
        pages = chunk.get("page_start", "?")
        page_end = chunk.get("page_end", pages)
        page_str = f"p.{pages}" if pages == page_end else f"pp.{pages}-{page_end}"
        ctype = chunk.get("chunk_type", "clause")
        parts.append(
            f"[{i}] ({ctype}) Section: {section} ({page_str}) chunk_id={chunk.get('chunk_id', '')}\n"
            f"{chunk.get('text', '').strip()}"
        )
    return "\n\n".join(parts)


def _format_session_history(turns: list) -> str:
    if not turns:
        return "(No prior conversation.)"
    lines: list[str] = []
    for turn in turns[-5:]:
        lines.append(f"User: {turn.question}")
        lines.append(f"Assistant: {turn.answer[:400]}")
    return "\n".join(lines)


def _asset_url(doc_id: str, asset_path: str) -> str | None:
    if not asset_path:
        return None
    filename = Path(asset_path).name
    return f"/api/v1/documents/{doc_id}/assets/{filename}"


def _chunks_to_sources(chunks: list[dict[str, Any]]) -> list[SourceCitation]:
    sources: list[SourceCitation] = []
    for r in chunks:
        asset_path = r.get("asset_path", "")
        sources.append(
            SourceCitation(
                chunk_id=r["chunk_id"],
                text=r["text"][:300] + ("..." if len(r["text"]) > 300 else ""),
                section_path=r["section_path"],
                page_start=r["page_start"],
                page_end=r["page_end"],
                score=r["score"],
                doc_id=r["doc_id"],
                chunk_type=r.get("chunk_type", "clause"),
                asset_url=_asset_url(r["doc_id"], asset_path),
            )
        )
    return sources


def _deduplicate_answer_lines(answer: str) -> str:
    lines = answer.splitlines()
    seen: set[str] = set()
    deduped: list[str] = []
    for line in lines:
        normalized = re.sub(r"^[\s\-\*\u2022\d.)]+", "", line.strip()).lower()
        if not normalized:
            deduped.append(line)
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(line)
    return "\n".join(deduped).strip()


def _log_interaction(payload: dict[str, Any]) -> None:
    INTERACTION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {**payload, "timestamp": datetime.now(timezone.utc).isoformat()}
    with INTERACTION_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _image_to_base64(doc_id: str, asset_path: str) -> str | None:
    full = DOCUMENTS_DIR / doc_id / asset_path
    if not full.exists():
        return None
    data = full.read_bytes()
    b64 = base64.standard_b64encode(data).decode("ascii")
    ext = full.suffix.lower().lstrip(".")
    mime = "png" if ext == "png" else "jpeg"
    return f"data:image/{mime};base64,{b64}"


class _AgentContext:
    def __init__(self, indexes: dict, allowed_docs: list[str], top_k: int):
        self.indexes = indexes
        self.allowed_docs = allowed_docs
        self.top_k = top_k
        # Keyed by (doc_id, chunk_id): chunk_id restarts at chunk_000001 in
        # every document, so it is not unique on its own.
        self.collected: dict[tuple[str, str], dict[str, Any]] = {}
        self.tool_calls: list[str] = []

    def _store(self, results: list[dict[str, Any]]) -> None:
        for r in results:
            key = (r.get("doc_id", ""), r.get("chunk_id") or r["text"][:80])
            self.collected[key] = r

    def semantic_search(self, query: str, top_k: int | None = None) -> str:
        k = top_k or self.top_k
        results = retrieve_across_documents(
            self.indexes, query, top_k=k, allowed_docs=self.allowed_docs
        )
        self._store(results)
        self.tool_calls.append(f"semantic_search:{query[:60]}")
        return json.dumps([{"chunk_id": r["chunk_id"], "text": r["text"][:200]} for r in results])

    def table_search(self, query: str, top_k: int | None = None) -> str:
        k = top_k or min(4, self.top_k)
        results = retrieve_across_documents(
            self.indexes,
            query,
            top_k=k,
            allowed_docs=self.allowed_docs,
            chunk_types=["table"],
        )
        if not results:
            results = retrieve_across_documents(
                self.indexes, f"table {query}", top_k=k, allowed_docs=self.allowed_docs
            )
        self._store(results)
        self.tool_calls.append(f"table_search:{query[:60]}")
        return json.dumps([{"chunk_id": r["chunk_id"], "text": r["text"][:300]} for r in results])

    def get_figure(self, chunk_id: str, doc_id: str) -> str:
        chunk = get_chunk_by_id(doc_id, chunk_id)
        if not chunk:
            return json.dumps({"error": "Figure chunk not found"})
        meta = chunk.get("meta") or {}
        asset_path = meta.get("asset_path", "")
        entry = {
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "text": chunk.get("text", ""),
            "asset_path": asset_path,
            "chunk_type": chunk.get("chunk_type", "image"),
            "page_start": chunk.get("page_start", 0),
            "page_end": chunk.get("page_end", 0),
            "section_path": chunk.get("section_path", ""),
            "score": 1.0,
            "hybrid_score": 1.0,
        }
        self._store([entry])
        self.tool_calls.append(f"get_figure:{chunk_id}")
        return json.dumps({"chunk_id": chunk_id, "caption": chunk.get("text", "")[:500]})


def _run_tool(ctx: _AgentContext, name: str, args: dict[str, Any]) -> str:
    if name == "semantic_search":
        return ctx.semantic_search(args.get("query", ""), args.get("top_k"))
    if name == "table_search":
        return ctx.table_search(args.get("query", ""), args.get("top_k"))
    if name == "get_figure":
        return ctx.get_figure(args.get("chunk_id", ""), args.get("doc_id", ""))
    return json.dumps({"error": f"Unknown tool: {name}"})


def _final_answer_with_vision(
    client,
    question: str,
    history: str,
    chunks: list[dict[str, Any]],
) -> str:
    context = _format_context(chunks)
    prompt = FINAL_ANSWER_PROMPT.format(context=context, history=history, question=question)

    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for chunk in chunks:
        if chunk.get("chunk_type") in ("image", "diagram"):
            asset_path = chunk.get("asset_path", "")
            if not asset_path:
                meta_path = (get_chunk_by_id(chunk["doc_id"], chunk["chunk_id"]) or {}).get(
                    "meta", {}
                ).get("asset_path", "")
                asset_path = meta_path
            if asset_path:
                data_url = _image_to_base64(chunk["doc_id"], asset_path)
                if data_url:
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        }
                    )

    try:
        if len(content) == 1:
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=DEFAULT_TEMPERATURE,
                max_tokens=DEFAULT_MAX_TOKENS,
            )
        else:
            response = client.chat.completions.create(
                model=VISION_MODEL,
                messages=[{"role": "user", "content": content}],
                temperature=DEFAULT_TEMPERATURE,
                max_tokens=DEFAULT_MAX_TOKENS,
            )
    except Exception as exc:
        raise_openai_error(exc)

    return response.choices[0].message.content or ""


def agent_answer(
    question: str,
    session_id: str | None = None,
    doc_ids: list[str] | None = None,
    top_k: int = DEFAULT_TOP_K,
) -> ChatResponse:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set")

    sid = session_service.get_or_create(session_id)
    last_question = session_service.get_last_question(sid)
    retrieval_query = _retrieval_query_for_turn(question, last_question)
    is_follow_up = _is_follow_up(question)

    ready_docs = index_service.list_ready_doc_ids()
    if not ready_docs:
        raise FileNotFoundError("No indexed documents available. Upload a PDF or Word document first.")

    allowed_docs = doc_ids if doc_ids else ready_docs
    allowed_docs = [d for d in allowed_docs if d in ready_docs]
    if not allowed_docs:
        raise ValueError("None of the requested doc_ids are indexed and ready.")

    indexes = {doc_id: index_service.load_index(doc_id) for doc_id in allowed_docs}
    ctx = _AgentContext(indexes, allowed_docs, top_k)
    client = make_openai_client()
    history = _format_session_history(session_service.get_history(sid))
    used_fallback = False
    skipped_final_call = False

    # Always retrieve first so we have excerpts even if OpenAI fails immediately.
    ctx.semantic_search(retrieval_query, top_k)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Question: {question}\nRetrieval hint: {retrieval_query}\n\nUse tools to find relevant excerpts, then answer.",
        },
    ]

    agent_ok = True
    agent_final_text = ""
    try:
        for _ in range(AGENT_MAX_ITERATIONS):
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                tools=AGENT_TOOLS,
                tool_choice="auto",
                temperature=DEFAULT_TEMPERATURE,
                max_tokens=DEFAULT_MAX_TOKENS,
            )
            msg = response.choices[0].message

            if not msg.tool_calls:
                # The loop terminated because the model wrote a final answer
                # (under SYSTEM_PROMPT's grounding rules) instead of calling a
                # tool. Keep it so we can skip the redundant final call below.
                agent_final_text = msg.content or ""
                break

            messages.append(msg.model_dump())
            for tool_call in msg.tool_calls:
                fn = tool_call.function
                args = json.loads(fn.arguments or "{}")
                result = _run_tool(ctx, fn.name, args)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    }
                )
    except Exception as exc:
        if ENABLE_RETRIEVAL_FALLBACK and openai_error_message(exc):
            logger.warning("Agent OpenAI call failed — using retrieval-only answer")
            agent_ok = False
        else:
            raise_openai_error(exc)

    if not ctx.collected:
        ctx.semantic_search(retrieval_query, top_k)

    retrieved = sorted(ctx.collected.values(), key=lambda x: x["score"], reverse=True)[:top_k]
    has_images = any(r.get("chunk_type") in ("image", "diagram") for r in retrieved)

    if agent_ok:
        # When the agent already produced a grounded text answer and there are
        # no figures to analyse visually, that answer stands — skip the extra
        # round-trip. Figures still go through the dedicated vision call, which
        # attaches the images; and if the loop ended without text (e.g. it hit
        # the iteration cap mid-search) we still synthesise an answer.
        if AGENT_SKIP_FINAL_CALL and agent_final_text.strip() and not has_images:
            answer = agent_final_text
            skipped_final_call = True
        else:
            try:
                answer = _final_answer_with_vision(client, question, history, retrieved)
            except Exception as exc:
                if ENABLE_RETRIEVAL_FALLBACK and openai_error_message(exc):
                    logger.warning("Final answer OpenAI call failed — using retrieval-only answer")
                    answer = retrieval_only_answer(question, retrieved)
                    used_fallback = True
                else:
                    raise_openai_error(exc)
    else:
        answer = retrieval_only_answer(question, retrieved)
        used_fallback = True
    answer = _deduplicate_answer_lines(answer)
    sources = _chunks_to_sources(retrieved)

    session_service.add_turn(sid, question, answer)
    _log_interaction(
        {
            "session_id": sid,
            "mode": "agent",
            "question": question,
            "retrieval_query": retrieval_query,
            "is_follow_up": is_follow_up,
            "doc_ids": allowed_docs,
            "tool_calls": ctx.tool_calls,
            "source_count": len(sources),
            "answer_preview": answer[:200],
            "retrieval_fallback": used_fallback,
            "skipped_final_call": skipped_final_call,
        }
    )

    return ChatResponse(answer=answer, sources=sources, session_id=sid)
