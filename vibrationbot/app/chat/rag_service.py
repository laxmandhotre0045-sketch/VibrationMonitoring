from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_K,
    ENABLE_RETRIEVAL_FALLBACK,
    INTERACTION_LOG_PATH,
    OPENAI_API_KEY,
    OPENAI_MODEL,
)
from app.schemas import ChatResponse, SourceCitation
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

RAG_PROMPT_TEMPLATE = """You are a document assistant. Answer the user's question using ONLY the information provided in <CONTEXT>.

Rules:
- Answer ONLY from the document excerpts in <CONTEXT>. Do not use outside knowledge.
- If the answer is not found in <CONTEXT>, respond exactly: "I do not know from the provided document excerpts."
- For follow-up questions, use <CONVERSATION_HISTORY> to understand what the user is asking about.
- Format your answer as one brief summary sentence followed by bullet points.
- Do not use markdown headings (no # or ##).
- Do not repeat the same bullet point twice.

<CONTEXT>
{context}
</CONTEXT>

<CONVERSATION_HISTORY>
{history}
</CONVERSATION_HISTORY>

Question: {question}

Answer:"""


def _format_retrieved_context(chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return "(No relevant document excerpts found.)"
    parts: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        section = chunk.get("section_path", "Unknown Section")
        pages = chunk.get("page_start", "?")
        page_end = chunk.get("page_end", pages)
        page_str = f"p.{pages}" if pages == page_end else f"pp.{pages}-{page_end}"
        parts.append(
            f"[{i}] Section: {section} ({page_str})\n{chunk.get('text', '').strip()}"
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


def rag_answer(
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
        raise FileNotFoundError("No indexed documents available. Upload a PDF first.")

    allowed_docs = doc_ids if doc_ids else ready_docs
    allowed_docs = [d for d in allowed_docs if d in ready_docs]
    if not allowed_docs:
        raise ValueError("None of the requested doc_ids are indexed and ready.")

    indexes = {doc_id: index_service.load_index(doc_id) for doc_id in allowed_docs}
    retrieved = retrieve_across_documents(
        indexes, retrieval_query, top_k=top_k, allowed_docs=allowed_docs
    )

    context = _format_retrieved_context(retrieved)
    history = _format_session_history(session_service.get_history(sid))

    prompt = RAG_PROMPT_TEMPLATE.format(
        context=context,
        history=history,
        question=question,
    )

    client = make_openai_client()
    used_fallback = False
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=DEFAULT_TEMPERATURE,
            max_tokens=DEFAULT_MAX_TOKENS,
        )
        answer = response.choices[0].message.content or ""
    except Exception as exc:
        if ENABLE_RETRIEVAL_FALLBACK and openai_error_message(exc):
            logger.warning("OpenAI unavailable — returning retrieval-only answer")
            answer = retrieval_only_answer(question, retrieved)
            used_fallback = True
        else:
            raise_openai_error(exc)
    answer = _deduplicate_answer_lines(answer)

    sources = [
        SourceCitation(
            chunk_id=r["chunk_id"],
            text=r["text"][:300] + ("..." if len(r["text"]) > 300 else ""),
            section_path=r["section_path"],
            page_start=r["page_start"],
            page_end=r["page_end"],
            score=r["score"],
            doc_id=r["doc_id"],
            chunk_type=r.get("chunk_type", "clause"),
            asset_url=(
                f"/api/v1/documents/{r['doc_id']}/assets/{Path(r['asset_path']).name}"
                if r.get("asset_path")
                else None
            ),
        )
        for r in retrieved
    ]

    session_service.add_turn(sid, question, answer)

    _log_interaction(
        {
            "session_id": sid,
            "question": question,
            "retrieval_query": retrieval_query,
            "is_follow_up": is_follow_up,
            "doc_ids": allowed_docs,
            "top_k": top_k,
            "source_count": len(sources),
            "answer_preview": answer[:200],
            "retrieval_fallback": used_fallback,
        }
    )

    return ChatResponse(answer=answer, sources=sources, session_id=sid)
