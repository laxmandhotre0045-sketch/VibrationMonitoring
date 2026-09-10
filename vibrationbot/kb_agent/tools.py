"""The tools the model may call.

Each tool returns a compact JSON string: the numbered label, where the passage
came from, and a truncated snippet. The *full* text never enters the tool
transcript — it goes into the PassageStore and reaches the answer prompt from
there.

That split matters for two reasons. Cost: four iterations x six excerpts of
full book text would spend most of the context window on passages the model
skims and discards. And fidelity: the answer is written from the stored text,
not from whatever survived being echoed through a tool message, so a passage
cannot be quietly truncated or reworded on its way to the answer.

The tools are built per question and closed over one store, which is why this
is a factory rather than a module-level list. Two concurrent questions get two
stores and cannot see each other's results.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from kb_agent import library
from kb_agent.config import KB_SNIPPET_CHARS, KB_TOP_K
from kb_agent.tools_iso import build_iso_tools

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Argument schemas — these become the tool signatures the model sees
# --------------------------------------------------------------------------


class SearchArgs(BaseModel):
    query: str = Field(
        ...,
        description=(
            "What to search for, phrased in the terminology the textbooks use. "
            "Prefer 'ball pass frequency outer race' over 'bearing noise', and "
            "'evaluation zones vibration severity' over 'is this too high'."
        ),
    )
    top_k: int = Field(
        KB_TOP_K, ge=1, le=12, description="How many excerpts to return."
    )


class TableArgs(BaseModel):
    query: str = Field(
        ...,
        description="What tabulated value to look for — a limit, threshold, zone boundary, or dimension.",
    )
    top_k: int = Field(4, ge=1, le=10)


class FigureArgs(BaseModel):
    query: str = Field(
        ..., description="What the figure or diagram should show."
    )
    top_k: int = Field(4, ge=1, le=10)


class PassageArgs(BaseModel):
    doc_id: str = Field(..., description="Document id, from a previous search result.")
    chunk_id: str = Field(..., description="Chunk id, from a previous search result.")


class NoArgs(BaseModel):
    pass


# --------------------------------------------------------------------------


def _render(passages: list[dict[str, Any]], note: str = "") -> str:
    """Compact JSON for the model. Snippets only; full text stays in the store."""
    if not passages:
        return json.dumps(
            {
                "results": [],
                "note": note
                or "Nothing matched. Try different wording, or a broader query.",
            }
        )
    return json.dumps(
        {
            "results": [
                {
                    "label": p["label"],
                    "doc_id": p.get("doc_id", ""),
                    "chunk_id": p.get("chunk_id", ""),
                    "type": p.get("chunk_type", "clause"),
                    "section": p.get("section_path", ""),
                    "page": p.get("page_start", 0),
                    "snippet": (p.get("text") or "")[:KB_SNIPPET_CHARS],
                }
                for p in passages
            ]
        }
    )


def build_tools(store: library.PassageStore) -> list[StructuredTool]:
    """Tools bound to one question's passage store."""

    def _search(query: str, top_k: int, chunk_types: list[str] | None) -> str:
        try:
            hits = library.search(query, store.doc_ids, top_k, chunk_types)
        except Exception as exc:  # noqa: BLE001 — a failed search is an answer, not a crash
            logger.warning("Search failed for %r: %s", query[:60], exc)
            return json.dumps({"results": [], "error": f"Search failed: {exc}"})
        if query.lower() not in {q.lower() for q in store.searches}:
            store.searches.append(query)
        return _render(store.add(hits))

    def search_documents(query: str, top_k: int = KB_TOP_K) -> str:
        """Search the indexed vibration books and standards by meaning.

        The first tool to reach for. Covers body text, tables and figure
        captions together. Call it more than once with different phrasings if
        the first result set is thin — a second, better-worded search costs far
        less than an answer built on weak evidence.
        """
        return _search(query, top_k, None)

    def search_tables(query: str, top_k: int = 4) -> str:
        """Search only tabulated content — limits, thresholds, zone boundaries, dimensions.

        Use when the answer is a number in a table rather than a sentence in a
        paragraph. Falls back to a general search when the corpus has no table
        chunk matching, so a thin result here is a real absence.
        """
        result = _search(query, top_k, ["table"])
        if json.loads(result).get("results"):
            return result
        return _search(f"table {query}", top_k, None)

    def search_figures(query: str, top_k: int = 4) -> str:
        """Search figure and diagram captions.

        Figures were captioned into searchable prose at ingest time, so this
        finds what a chart *shows*. The caption is a reading of the figure, not
        the figure itself — say so if an answer leans on one.
        """
        return _search(query, top_k, ["image", "diagram"])

    def get_passage(doc_id: str, chunk_id: str) -> str:
        """Fetch one passage in full, by the ids from a search result.

        Search returns truncated snippets. Call this when a snippet is cut off
        mid-definition, mid-formula or mid-table and the rest of it decides the
        answer.
        """
        found = library.passage(doc_id, chunk_id)
        if not found:
            return json.dumps(
                {"error": f"No passage {chunk_id} in {doc_id}. Check the ids from the search result."}
            )
        stored = store.add([found])
        target = stored[0] if stored else found
        return json.dumps(
            {
                "label": target.get("label"),
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "section": found.get("section_path", ""),
                "page_start": found.get("page_start", 0),
                "page_end": found.get("page_end", 0),
                "text": found.get("text", ""),
            }
        )

    def list_indexed_documents() -> str:
        """List the documents available to search, with their sizes.

        Use when the question names a specific book or standard, to check it is
        actually in the corpus before answering as though it were.
        """
        return json.dumps({"documents": library.list_documents()})

    specs = [
        (search_documents, "search_documents", SearchArgs),
        (search_tables, "search_tables", TableArgs),
        (search_figures, "search_figures", FigureArgs),
        (get_passage, "get_passage", PassageArgs),
        (list_indexed_documents, "list_indexed_documents", NoArgs),
    ]
    return [
        StructuredTool.from_function(func=func, name=name, args_schema=schema)
        for func, name, schema in specs
    ] + build_iso_tools()
