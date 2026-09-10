from __future__ import annotations

import logging
import re
import threading
from typing import Any

from langchain_community.vectorstores import FAISS

from app.config import RERANK_POOL_K, RERANKER_MODEL, RETRIEVAL_CANDIDATE_K

logger = logging.getLogger(__name__)

STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "to", "of", "in",
    "for", "on", "with", "at", "by", "from", "as", "into", "through",
    "during", "before", "after", "above", "below", "between", "under",
    "again", "further", "then", "once", "here", "there", "when", "where",
    "why", "how", "all", "each", "few", "more", "most", "other", "some",
    "such", "no", "nor", "not", "only", "own", "same", "so", "than",
    "too", "very", "and", "but", "or", "if", "because", "until", "while",
    "what", "which", "who", "whom", "this", "that", "these", "those",
    "am", "i", "me", "my", "we", "our", "you", "your", "he", "she", "it",
    "they", "them", "their", "about", "tell", "explain", "detail", "more",
}

TABLE_SIGNALS = {"table", "row", "column", "value", "values", "data", "cell", "cells"}
FIGURE_SIGNALS = {
    "chart", "graph", "figure", "diagram", "plot", "image", "picture",
    "visual", "trend", "axis", "axes",
}

FOLLOW_UP_PATTERNS = [
    re.compile(p)
    for p in (
        r"\bexplain\s+in\s+detail\b",
        r"\btell\s+me\s+more\b",
        r"\bmore\s+details?\b",
        r"\belaborate\b",
        r"\bexpand\s+on\b",
        r"\bcan\s+you\s+explain\b",
        r"\bwhat\s+about\s+that\b",
        r"\bgo\s+deeper\b",
        r"\bclarify\b",
        r"\bin\s+more\s+detail\b",
    )
]

MULTI_SPACE_RE = re.compile(r"\s+")

_reranker = None
_reranker_lock = threading.Lock()


def _get_reranker():
    global _reranker
    with _reranker_lock:
        if _reranker is None:
            from sentence_transformers import CrossEncoder

            _reranker = CrossEncoder(RERANKER_MODEL)
        return _reranker


def _extract_keywords(query: str) -> set[str]:
    tokens = re.findall(r"[a-zA-Z0-9]+", query.lower())
    return {t for t in tokens if len(t) > 2 and t not in STOPWORDS}


def _is_follow_up(question: str) -> bool:
    q = question.strip().lower()
    return any(p.search(q) for p in FOLLOW_UP_PATTERNS)


def _retrieval_query_for_turn(question: str, last_question: str | None) -> str:
    if _is_follow_up(question) and last_question:
        return f"{last_question} {question}".strip()
    return question.strip()


def _keyword_score(text: str, keywords: set[str]) -> float:
    if not keywords:
        return 0.0
    text_lower = text.lower()
    hits = sum(1 for kw in keywords if kw in text_lower)
    return hits / len(keywords)


def _chunk_type_boost(query: str, chunk_type: str) -> float:
    q = query.lower()
    if chunk_type == "table" and any(s in q for s in TABLE_SIGNALS):
        return 0.12
    if chunk_type in ("image", "diagram") and any(s in q for s in FIGURE_SIGNALS):
        return 0.12
    return 0.0


def _meta_asset_path(meta: dict[str, Any]) -> str:
    return meta.get("asset_path", "") or ""


def _normalize_text(text: str) -> str:
    """Whitespace/case-insensitive key for collapsing duplicate passages."""
    return MULTI_SPACE_RE.sub(" ", (text or "").strip().lower())


def _rerank_candidates(
    query: str, candidates: list[dict[str, Any]], top_k: int
) -> list[dict[str, Any]]:
    """Rescore candidates with the cross-encoder and return the best ``top_k``.

    Must be called once on the *merged* cross-document pool. Reranking per
    document and then merging would compare cross-encoder logits (unbounded,
    frequently negative) against hybrid scores (0-1) — an incoherent ordering.

    On any reranker failure the hybrid ordering is preserved, so ``score``
    stays on a single scale either way.
    """
    if len(candidates) <= top_k:
        return candidates[:top_k]
    pool = candidates[:RERANK_POOL_K]
    try:
        reranker = _get_reranker()
        scores = reranker.predict([[query, c["text"]] for c in pool])
    except Exception as exc:  # noqa: BLE001 — degrade to hybrid ranking
        logger.warning("Reranker unavailable, falling back to hybrid scores: %s", exc)
        return candidates[:top_k]

    for candidate, score in zip(pool, scores):
        candidate["score"] = round(float(score), 4)
    pool.sort(key=lambda x: x["score"], reverse=True)
    return pool[:top_k]


def _candidates_from_index(
    vectorstore: FAISS,
    query: str,
    top_k: int = 6,
    chunk_types: list[str] | None = None,
    query_vector: list[float] | None = None,
) -> list[dict[str, Any]]:
    """Hybrid-scored candidates from one document index (no reranking).

    Returns the full deduped candidate list rather than ``top_k`` so the caller
    can rerank a merged pool. ``score`` and ``hybrid_score`` start equal;
    reranking later overwrites only ``score``.

    ``query_vector`` lets the caller embed the query once and reuse it across
    every document index; ``similarity_search_with_score`` would otherwise
    re-embed the identical string per index.
    """
    candidate_k = max(RETRIEVAL_CANDIDATE_K, top_k * 5)
    if query_vector is None:
        results = vectorstore.similarity_search_with_score(query, k=candidate_k)
    else:
        results = vectorstore.similarity_search_with_score_by_vector(
            query_vector, k=candidate_k
        )
    keywords = _extract_keywords(query)

    scored: list[dict[str, Any]] = []
    for doc, distance in results:
        meta = doc.metadata or {}
        chunk_type = meta.get("chunk_type", "clause")

        if chunk_types and chunk_type not in chunk_types:
            continue

        vector_score = 1.0 / (1.0 + float(distance))
        kw_score = _keyword_score(doc.page_content, keywords)
        type_boost = _chunk_type_boost(query, chunk_type)
        combined = round(0.7 * vector_score + 0.3 * kw_score + type_boost, 4)

        scored.append(
            {
                "chunk_id": meta.get("chunk_id", ""),
                "chunk_type": chunk_type,
                "text": doc.page_content,
                "node_id": meta.get("node_id", ""),
                "page_start": int(meta.get("page_start", 0)),
                "page_end": int(meta.get("page_end", 0)),
                "section_path": meta.get("section_path", ""),
                "doc_id": meta.get("doc_id", ""),
                "asset_path": _meta_asset_path(meta),
                "score": combined,
                "hybrid_score": combined,
            }
        )

    return scored


def retrieve_across_documents(
    indexes: dict[str, FAISS],
    query: str,
    top_k: int = 6,
    allowed_docs: list[str] | None = None,
    chunk_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    doc_ids = allowed_docs if allowed_docs else list(indexes.keys())
    active = [d for d in doc_ids if d in indexes]

    # Embed once and reuse across indexes. Equivalent to what
    # similarity_search_with_score does internally (same embed_query call, so
    # the BGE query_instruction prefix still applies) — just not N times.
    query_vector: list[float] | None = None
    if len(active) > 1:
        try:
            from app.retrieval.embeddings import get_embeddings

            query_vector = get_embeddings().embed_query(query)
        except Exception as exc:  # noqa: BLE001 — fall back to per-index embedding
            logger.warning("Could not pre-embed query, falling back: %s", exc)

    # NB: this loop is intentionally serial. Per-index FAISS search is ~7ms
    # even across 24 indexes; the cross-encoder rerank below is ~900ms — over
    # 99% of retrieval time. Threading the search measurably added overhead for
    # no gain, so the parallelism was removed. Speed up retrieval by shrinking
    # RERANK_POOL_K or the candidate set, not by parallelising search.
    candidates: list[dict[str, Any]] = []
    for doc_id in active:
        candidates.extend(
            _candidates_from_index(
                indexes[doc_id],
                query,
                top_k=top_k,
                chunk_types=chunk_types,
                query_vector=query_vector,
            )
        )

    candidates.sort(key=lambda x: x["hybrid_score"], reverse=True)

    # Two-level dedupe.
    #
    # 1. Identity: chunk_id is only unique *within* a document (each doc
    #    restarts at chunk_000001), so the key must include doc_id — otherwise
    #    unrelated chunks sharing an id across documents collide and get
    #    dropped.
    # 2. Content: the same passage often exists in several indexed documents
    #    (re-uploads, overlapping editions). Those are distinct chunks by
    #    identity but redundant in context, so collapse equal text and keep the
    #    best-scoring copy. Candidates are pre-sorted, so first seen wins.
    deduped: list[dict[str, Any]] = []
    seen_ids: set[tuple[str, str]] = set()
    seen_text: set[str] = set()
    for item in candidates:
        identity = (item["doc_id"], item["chunk_id"] or item["text"][:80])
        if identity in seen_ids:
            continue
        text_key = _normalize_text(item["text"])
        if text_key and text_key in seen_text:
            continue
        seen_ids.add(identity)
        seen_text.add(text_key)
        deduped.append(item)

    return _rerank_candidates(query, deduped, top_k)
