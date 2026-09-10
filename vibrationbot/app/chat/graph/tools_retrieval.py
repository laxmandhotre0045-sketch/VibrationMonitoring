"""Retrieval tools — thin wrappers over the existing retrieval service.

Nothing here reimplements search. ``retrieve_across_documents`` already does
cross-index merging, hybrid scoring, two-level dedupe and cross-encoder
reranking, and it is exercised by the existing test suite. The graph gets the
same retrieval the legacy agent mode gets.

The tools return a compact JSON string for the model and stash the full chunk
dicts on a per-turn context object, so the retrieved text reaches the answer
prompt without also being pasted into the tool-call transcript.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.retrieval.chunks import get_chunk_by_id
from app.retrieval.index_service import index_service
from app.retrieval.retrieval_service import retrieve_across_documents

logger = logging.getLogger(__name__)


class RetrievalContext:
    """Per-turn accumulator for retrieved chunks.

    Keyed by ``(doc_id, chunk_id)``: chunk ids restart at chunk_000001 in every
    document, so chunk_id alone collides across documents and would silently
    drop passages.
    """

    def __init__(self, allowed_docs: list[str], top_k: int) -> None:
        self.allowed_docs = allowed_docs
        self.top_k = top_k
        self.collected: dict[tuple[str, str], dict[str, Any]] = {}
        self.calls: list[str] = []
        self._indexes: dict[str, Any] | None = None

    @property
    def indexes(self) -> dict[str, Any]:
        if self._indexes is None:
            self._indexes = {
                doc_id: index_service.load_index(doc_id) for doc_id in self.allowed_docs
            }
        return self._indexes

    def store(self, results: list[dict[str, Any]]) -> None:
        for result in results:
            key = (result.get("doc_id", ""), result.get("chunk_id") or result["text"][:80])
            self.collected[key] = result

    def best(self, limit: int | None = None) -> list[dict[str, Any]]:
        ordered = sorted(self.collected.values(), key=lambda r: r["score"], reverse=True)
        return ordered[: limit or self.top_k]

    def search(
        self, query: str, top_k: int | None = None, chunk_types: list[str] | None = None
    ) -> list[dict[str, Any]]:
        if not self.allowed_docs:
            return []
        results = retrieve_across_documents(
            self.indexes,
            query,
            top_k=top_k or self.top_k,
            allowed_docs=self.allowed_docs,
            chunk_types=chunk_types,
        )
        self.store(results)
        return results


def _compact(results: list[dict[str, Any]], text_chars: int) -> str:
    if not results:
        return json.dumps({"results": [], "note": "No matching excerpts found."})
    return json.dumps(
        {
            "results": [
                {
                    "chunk_id": r.get("chunk_id", ""),
                    "doc_id": r.get("doc_id", ""),
                    "section": r.get("section_path", ""),
                    "page": r.get("page_start", 0),
                    "type": r.get("chunk_type", "clause"),
                    "text": (r.get("text") or "")[:text_chars],
                }
                for r in results
            ]
        }
    )


class SemanticSearchArgs(BaseModel):
    query: str = Field(..., description="What to search for, in the terminology the textbooks use")
    top_k: int = Field(6, ge=1, le=12, description="Number of excerpts to return")


class TableSearchArgs(BaseModel):
    query: str = Field(..., description="What tabular data to look for")
    top_k: int = Field(4, ge=1, le=10)


class FigureArgs(BaseModel):
    chunk_id: str = Field(..., description="chunk_id of the figure, from a previous search result")
    doc_id: str = Field(..., description="doc_id the figure belongs to")


def build_retrieval_tools(ctx: RetrievalContext) -> list[StructuredTool]:
    """Build tools bound to one turn's retrieval context."""

    def semantic_search(query: str, top_k: int = 6) -> str:
        """Search the indexed vibration standards and textbooks by meaning.

        Use for theory, mechanisms, diagnostic guidance, and anything the
        standards say. Prefer the technical terms the books use.
        """
        results = ctx.search(query, top_k=top_k)
        ctx.calls.append(f"semantic_search:{query[:60]}")
        return _compact(results, 400)

    def table_search(query: str, top_k: int = 4) -> str:
        """Search only table content — limits, thresholds, zone boundaries, bearing dimensions.

        Use when the answer is a tabulated number rather than prose.
        """
        results = ctx.search(query, top_k=top_k, chunk_types=["table"])
        if not results:
            # Table chunks may not exist for this query; a prefixed general
            # search often still surfaces the right passage.
            results = ctx.search(f"table {query}", top_k=top_k)
        ctx.calls.append(f"table_search:{query[:60]}")
        return _compact(results, 600)

    def get_figure(chunk_id: str, doc_id: str) -> str:
        """Load a specific figure or chart by chunk_id so it can be examined visually."""
        chunk = get_chunk_by_id(doc_id, chunk_id)
        ctx.calls.append(f"get_figure:{chunk_id}")
        if not chunk:
            return json.dumps({"error": "Figure not found"})
        meta = chunk.get("meta") or {}
        entry = {
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "text": chunk.get("text", ""),
            "asset_path": meta.get("asset_path", ""),
            "chunk_type": chunk.get("chunk_type", "image"),
            "page_start": chunk.get("page_start", 0),
            "page_end": chunk.get("page_end", 0),
            "section_path": chunk.get("section_path", ""),
            # Explicitly requested, so it outranks anything the ranker found.
            "score": 1.0,
            "hybrid_score": 1.0,
        }
        ctx.store([entry])
        return json.dumps({"chunk_id": chunk_id, "caption": chunk.get("text", "")[:500]})

    return [
        StructuredTool.from_function(
            func=semantic_search, name="semantic_search", args_schema=SemanticSearchArgs
        ),
        StructuredTool.from_function(
            func=table_search, name="table_search", args_schema=TableSearchArgs
        ),
        StructuredTool.from_function(
            func=get_figure, name="get_figure", args_schema=FigureArgs
        ),
    ]
