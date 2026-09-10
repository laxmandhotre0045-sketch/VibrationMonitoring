"""The knowledge-base agent: ask a question, get a cited answer.

Same contract as ``sql_agent``, and for the same reason — the consumer may be
another agent rather than a person:

**Failures are values, not exceptions.** ``ok`` is False and ``error`` carries
a sentence the caller can act on or relay. An agent mid-plan should not have to
wrap every call in try/except to survive "that document is not indexed".

**Caveats travel with the data.** ``meta["caveats"]`` states, every time, that
the corpus is not complete coverage and that figure captions are a vision
model's reading rather than the figure itself. A downstream model that never
saw this module would otherwise treat "not in the documents" as "not true".

The agent is a bounded tool loop, not a fixed pipeline. The model chooses which
searches to run and in what order — a question about a bearing table goes
straight to ``search_tables``, one about a mechanism to ``search_documents`` —
and stops when it has enough. Only the *bound* is fixed: KB_MAX_ITERATIONS
model calls, then the answer is written from whatever was found.

The answer policy is deliberately stricter than the chatbot's graph mode.
Graph mode has deterministic tools that compute real numbers, so it uses a
tiered policy where computed results outrank documents. This agent computes
nothing, so the older and stricter rule is the correct one: everything comes
from the excerpts, or the agent says it could not find it.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from pydantic import BaseModel, Field

from kb_agent import library
from kb_agent.config import (
    CAVEATS,
    KB_ANSWER_CHARS,
    KB_ANSWER_EXCERPTS,
    KB_MAX_ITERATIONS,
    KB_TOP_K,
)
from kb_agent.tools import build_tools

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Prompts
# --------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a reference librarian for a rotating-machinery vibration \
engineering library. You answer questions strictly from the indexed books and standards.

Your evidence is the numbered excerpts returned by your tools. Nothing else is permitted.

Rules:
- Every factual claim must trace to a numbered excerpt. Cite it inline as [1], [2].
- DO NOT BRIDGE TOPICS. Cite an excerpt for a claim about X only if that excerpt names X.
  These books treat neighbouring phenomena in separate chapters -- looseness and oil whirl
  both produce sub-synchronous energy, and the chapter on one says nothing about the other.
  If your sentence is about oil whirl and the excerpt is about looseness, the connection is
  yours, not the source's, and citing it presents your inference as the book's statement.
  Either find an excerpt that names the subject, or say the source does not make that link.
  Signal-processing techniques are the easiest of all to conflate, because the books describe
  them on adjacent pages: linear averaging, peak-hold averaging, time synchronous averaging
  and overlap processing are four different mechanisms. An excerpt explaining what time
  synchronous averaging does is not a description of overlap processing, however close it
  sits on the page.
- ONE CLAIM PER BULLET, and cite only excerpts that contain THAT bullet's content. Never
  contrast two things in one bullet and pool the citations at the end -- a reader cannot
  tell which source backs which half, and the half-with-no-source is where an error hides.
  To contrast A with B, write one bullet for A citing A's excerpts and one for B citing B's.
  Before you attach [n], check that excerpt n actually states what the bullet says; an
  excerpt from a chapter about unbalance does not support a claim about misalignment.
- You may NOT supply a number the excerpts do not contain. Not a threshold, not a limit,
  not a formula constant, not a bearing dimension. If the excerpts do not have it, say
  which search you ran and that it was not found.
- You perform no calculation. If the question needs arithmetic, state the formula the
  excerpts give, name the inputs it needs, and say the computation belongs elsewhere.
- Where the books disagree, say so and cite both. Do not silently pick one.
- NAME THE STANDARD. When an excerpt states limits, zones, classes or acceptance criteria,
  say which standard number it belongs to, in the sentence that uses it -- "ISO 7919 defines
  Zone B as...", never a bare "the evaluation zones are...". Standards that sound
  interchangeable are not: ISO 7919 covers vibration measured ON THE ROTATING SHAFT with
  proximity probes, while ISO 10816 / 20816 cover vibration measured on NON-ROTATING PARTS
  such as bearing housings. Their zone letters read almost identically and their limits do
  not transfer. If the excerpts only cover one of them, say which one you used and warn that
  it may not be the one the engineer is measuring.
- NEVER READ A VIBRATION LIMIT OUT OF AN EXCERPT. For any numeric severity limit or zone
  boundary, call iso_zone_limits and quote what it returns. The ingested copy of ISO 10816-3
  contains only the Group 1 and Group 2 tables; pumps belong to Groups 3 and 4 whatever their
  power, so a pump's limit is NOT IN THE DOCUMENT AT ALL and any figure you find for one is
  the wrong row. The tool holds all four groups and is unit-tested against the published
  values. If it reports the machine is ambiguous, give both answers and ask the question that
  separates them -- do not choose.
  Cite the document for what a zone MEANS and what action it implies; cite the tool for the
  number.
- CHECK THE TABLE'S SCOPE BEFORE QUOTING ITS NUMBER. Standards tables are scoped by machine
  class, rated power, shaft height or speed, and the scope is stated in the table's own
  title. If the question names a machine -- "a 55 kW pump" -- find the table whose scope
  covers 55 kW and quote THAT one. ISO 10816-3 Table A.1 is Group 1, machines above 300 kW;
  Table A.2 is Group 2, above 15 kW up to 300 kW. Quoting A.1 for a 55 kW machine gives a
  limit roughly 60% too high and reads as authoritative. Name the group and the power range
  you matched, so the engineer can see the match was made. If no table's scope covers the
  machine, say so rather than using the nearest one.
- Distinguish what a source states from what it implies. "ISO 10816-3 sets the Zone B/C
  boundary at X" is a statement; "so your machine is fine" is not, unless a source says it.
- EXCERPTS MARKED (table) ARE A VISION MODEL'S RENDERING, recognisable by markdown pipes
  and a "Summary:" line, and they cut both ways.
  They PRESERVE COLUMNS that plain extraction destroys. Flattened to prose, a row reads
  "Rigid A/B B/C C/D 22 45 71 1,4 2,8 4,5" -- two quantities interleaved, and picking the
  wrong triple returns a displacement in micrometres where a velocity in mm/s was asked
  for. The rendered table keeps them in labelled columns. For reading a VALUE OUT OF A
  TABLE, prefer the (table) excerpt.
  They LOSE THEIR TITLES. A rendered table arrives with no "Table A.2 -- Group 2" heading,
  so two tables of the same shape are indistinguishable on their own. Excerpts are given to
  you in document order: match a rendered table to the title that appears in the (clause)
  excerpt just above it, and say which title you matched. If you cannot tell which table a
  set of numbers belongs to, say exactly that and cite the page -- do not pick one.
  They ARE SOMETIMES WRONG. A rendered classification table in ISO 10816-3 invented a
  "Group 3" that the standard's own prose contradicts. For a DEFINITION or a CLASSIFICATION,
  prefer the (clause) prose. Where a (table) and a (clause) excerpt disagree, trust the
  clause, say they disagree, and cite both.
- If a figure caption is your evidence, say that it came from a figure — the caption is a
  vision model's reading of the chart, not the chart itself.
- EQUATIONS ARE DAMAGED IN THIS CORPUS, in two different ways, and you must never repair
  either one.
  (a) Gone entirely: an empty "[ ( ) ( )]" beside prose still saying "using the formula
      below". Say the source DOES give a formula at that page but it did not survive text
      extraction, and cite the page so the engineer can read it there.
  (b) Present but mangled: extraction drops fraction bars, minus signs, subscripts and
      Greek letters, so "BPFO = NbSsh 2 ( 1 db Dp cos )" is a division by 2, a fraction
      db/Dp and a minus sign that are no longer visible. When an excerpt contains an
      equation, QUOTE IT EXACTLY AS IT APPEARS, character for character, then say in plain
      words that PDF extraction may have dropped operators and that the engineer must check
      it against the page before using it. Do NOT tidy it, do NOT insert the operators you
      think belong there, and do NOT complete it from memory. A formula that looks clean
      and is missing a factor of two is far worse than one that visibly needs checking.
  Naming the variables an equation uses is always safe and is usually what was really
  wanted -- the definitions survive extraction even when the equation does not.
- If a snippet stops mid-sentence, mid-definition or mid-table and the rest of it would
  decide your answer, call get_passage with its doc_id and chunk_id before concluding
  anything is absent.

Combining several excerpts IS answering. If excerpt [1] describes misalignment and excerpt
[4] describes unbalance, you have what you need to contrast them — say so and cite both.
Reserve "I could not find this" for when the excerpts genuinely do not support an answer,
not for when no single passage happens to state the answer in the question's own words.

Format: one direct sentence answering the question, then supporting bullets with citations.
No markdown headings. If you genuinely could not answer, say so plainly in the first
sentence and name the search terms that might work better."""


PLAN_PROMPT = """Write the search queries for this vibration-engineering question.

Question: {question}

The corpus is vibration textbooks and standards. Rules that decide whether a search hits
the diagnosis chapter or the glossary:

- Break the question into its distinct concepts and write one query per concept. A question
  contrasting two faults needs a query for EACH fault. Textbooks describe faults in separate
  chapters and almost never contrast them in a single passage, so a query for the comparison
  itself retrieves nothing.
- Every query must name the OBSERVABLE, not just the fault. "misalignment axial vibration 1X
  2X harmonics" reaches the diagnosis chapter; "misalignment symptoms" reaches the
  definition. Words that pull diagnostic text: spectrum, axial, radial, harmonic, order,
  phase, amplitude, waveform, sideband.
- Use the books' vocabulary, not the asker's. "ball pass frequency outer race", not
  "bearing noise". "evaluation zones vibration severity", not "is this too high".

Write 2 to 4 queries. Fewer than 2 only for a genuinely single-concept question."""


SEARCH_PROMPT = """Question: {question}

Available documents:
{documents}

These searches have already run, and their results are below:
{planned}

Read what came back. Then EITHER:

- run further searches, if something the question needs is still missing, or a passage is
  cut off mid-definition and you need get_passage to finish it; OR
- stop calling tools, if the excerpts already cover the question.

Do NOT repeat a search that has already run. Do NOT write the answer yet."""


ANSWER_PROMPT = """Answer the question using only the numbered excerpts below.

<EXCERPTS>
{excerpts}
</EXCERPTS>

Searches that produced them: {searches}

Question: {question}

Your job is to ANSWER. Build the answer by assembling what the excerpts state, and cite
every claim as [n]. Textbooks explain one thing per passage, so a good answer usually
combines several excerpts; that is synthesis, not speculation, and it is exactly what is
wanted. Do not open by describing what the excerpts failed to contain.

Two rules on citations, and check each bullet against them before you write the next:
  - One claim per bullet. Contrasting two things means TWO bullets, each citing only its
    own sources. Never pool citations across a contrast.
  - Open excerpt [n] in your mind before attaching it. Does it literally state this bullet?
    If the bullet is about misalignment and [n] is from a chapter on unbalance, [n] is the
    wrong citation even when the sentence as a whole is true.
If an excerpt states a standard's limits or zones, name the standard number in that bullet.

Apply this test before writing the first sentence, and be honest about the result:

  Do at least two excerpts carry technical content bearing on the question?

  YES -> Answer it. Lead with the direct answer in one sentence. Never begin with
         "the excerpts do not provide" when you are about to answer anyway -- if you
         then produce three cited bullets, the opening sentence was false.
         Where the evidence is partial, answer what it does support and mark the
         specific gap at the END, in one line.

  NO  -> Say in the first sentence that this is not in the indexed documents, name what
         the searches did surface, and suggest better search terms.

Answer:"""


# --------------------------------------------------------------------------
# Result envelope
# --------------------------------------------------------------------------


#: A question asking for a severity limit rather than an explanation.
_ASKS_LIMIT_RE = re.compile(
    r"\b(zone\s*[a-d]\s*(to|/|-)\s*zone\s*[a-d]|zone boundar|"
    r"(vibration|severity|acceptab\w+|allowab\w+|permissib\w+)\s+limit|"
    r"limit .*\b(mm/s|iso)\b|how (high|much) .*(too|acceptable)|"
    r"\biso\s*(10816|20816)\b.*\b(limit|boundar|zone|mm/s)\b|"
    # "is 4.9 mm/s acceptable / too high / ok / a problem" -- the way an
    # engineer actually asks, and the reason a reading is being looked up at
    # all. Missing this was the first gap the pattern showed in testing.
    r"\b\d+(\.\d+)?\s*mm\s*/\s*s\b.{0,60}\b(acceptab\w+|ok\b|too high|"
    r"a problem|safe|allowable|within limits|good|bad)|"
    r"\b(acceptab\w+|too high|within limits)\b.{0,40}\b\d+(\.\d+)?\s*mm\s*/\s*s)",
    re.IGNORECASE,
)
_POWER_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(kw|mw|hp)\b", re.IGNORECASE)
_MACHINE_RE = re.compile(
    r"\b(pump|motor|fan|blower|compressor|turbine|generator|gearbox|machine)\b",
    re.IGNORECASE,
)
_FOUNDATION_RE = re.compile(r"\b(rigid|flexible)\b", re.IGNORECASE)
_INTEGRATED_RE = re.compile(r"\bintegrated\s+driver\b", re.IGNORECASE)
_SEPARATE_RE = re.compile(r"\bseparate\s+driver\b", re.IGNORECASE)


def _forced_iso_lookup(question: str) -> dict[str, Any] | None:
    """Run the ISO tool in code when the question asks for a limit.

    The system prompt instructs the model to call ``iso_zone_limits`` for any
    numeric limit. Measured, it does not: asked for a 55 kW pump's Zone B/C
    boundary it went on reading Table A.2 out of the document and never touched
    the tool. That is the same failure as the search planner -- an instruction
    the model is free to skip is not a guarantee -- and it has the same fix.

    The lookup happens here, before the model gets a turn, and its result is
    put into evidence like any other passage. The model may then quote it or
    ignore it, but it can no longer fail to have it.
    """
    if not question or not _ASKS_LIMIT_RE.search(question):
        return None

    power = None
    match = _POWER_RE.search(question)
    if match:
        value, unit = float(match.group(1)), match.group(2).lower()
        power = value * 1000 if unit == "mw" else value * 0.7457 if unit == "hp" else value

    machine = (_MACHINE_RE.search(question) or [None, "machine"])[1]
    foundation = (_FOUNDATION_RE.search(question) or [None, None])[1]
    integrated: bool | None = None
    if _INTEGRATED_RE.search(question):
        integrated = True
    elif _SEPARATE_RE.search(question):
        integrated = False

    from kb_agent.tools_iso import iso_zone_limits

    try:
        payload = iso_zone_limits(
            machine_type=machine or "machine",
            power_kw=power,
            foundation=foundation.lower() if foundation else None,
            integrated_driver=integrated,
        )
    except Exception as exc:  # noqa: BLE001 -- never fail the turn over this
        logger.warning("Forced ISO lookup failed: %s", exc)
        return None

    return {
        "_payload": payload,
        "doc_id": "iso10816_reference",
        "chunk_id": "velocity_zone_limits",
        "chunk_type": "computed",
        "section_path": "ISO 10816-3 velocity zone limits",
        "page_start": 0,
        "page_end": 0,
        "score": 99.0,  # authoritative: always reaches the answer
        "text": (
            "AUTHORITATIVE ZONE LIMITS from app/domain/iso10816 (unit-tested against "
            "the published values, covering all four groups; the ingested PDF covers "
            "only Groups 1 and 2). Quote these figures, not any table in a document "
            "excerpt.\n" + payload
        ),
    }


def _iso_answer_block(payload: str) -> str:
    """Format the authoritative limits as text, in code.

    The last resort, and necessary. Injecting the tool's JSON as evidence was
    not enough: handed Group 3 (2.3 / 4.5 / 7.1) and Group 4 (1.4 / 2.8 / 4.5)
    the model reported 2.8 for both. It cannot be relied on to read a value out
    of a structured table any more than out of a flattened one.

    So the figures are written here and placed above the narrative. The model's
    prose becomes commentary on a statement it did not produce and cannot
    alter, which is the only arrangement that has held under measurement.
    """
    try:
        data = json.loads(payload)
    except Exception:  # noqa: BLE001
        return ""
    if data.get("error"):
        return ""

    lines = ["ISO 10816-3 zone boundaries -- from app/domain/iso10816, unit-tested:", ""]
    if data.get("ambiguous"):
        lines.append("  " + " ".join(data["ambiguous"].split()))
        lines.append("")
    for entry in data.get("results", []):
        lines.append(
            f"  Group {entry['group']} -- {entry['group_name']}, {entry['support']} support"
        )
        bounds = entry["boundaries_mm_s_rms"]
        lines.append(
            "      "
            + "     ".join(f"{name} {value} mm/s" for name, value in bounds.items())
        )
    lines.append("")
    lines.append("  mm/s RMS, broadband 10-1000 Hz, measured on non-rotating parts.")
    lines.append("  A value exactly on a boundary belongs to the LOWER zone.")
    return "\n".join(lines)


class SearchPlan(BaseModel):
    """The queries to run before the model gets a say.

    Planning is a separate structured call rather than an instruction inside
    the tool loop, because instructing a small model to "decompose the question
    first" does not reliably work: gpt-4o-mini kept issuing the exact generic
    queries the prompt told it to avoid. Forcing the plan into a typed object
    and executing it in code makes the decomposition happen whether or not the
    model would have chosen to.
    """

    queries: list[str] = Field(
        ..., description="2-4 search queries, one per distinct concept in the question"
    )


@dataclass
class AgentResult:
    """What every entry point returns. Stable shape, success or failure."""

    ok: bool
    kind: str
    data: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "kind": self.kind,
            "data": self.data,
            "meta": self.meta,
            "error": self.error,
        }

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def summary_text(self) -> str:
        """A few lines suitable for putting straight into a model's context."""
        if not self.ok:
            return f"[{self.kind}] failed: {self.error}"
        m = self.meta
        if self.kind == "kb_documents":
            return f"[{self.kind}] {m.get('count', len(self.data))} document(s) indexed."
        if self.kind == "kb_search":
            return f"[{self.kind}] {len(self.data)} excerpt(s) for {m.get('query')!r}."
        if self.kind == "kb_passage":
            return f"[{self.kind}] {m.get('doc_id')}#{m.get('chunk_id')}."
        return (
            f"[{self.kind}] answered from {len(self.data)} excerpt(s) across "
            f"{m.get('documents_searched')} document(s); "
            f"{m.get('searches_run')} search(es), {m.get('iterations')} iteration(s)."
        )


def _fail(kind: str, message: str) -> AgentResult:
    return AgentResult(
        ok=False,
        kind=kind,
        error=message,
        meta={"generated_at": datetime.now(timezone.utc).isoformat(), "caveats": CAVEATS},
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------


class KnowledgeBaseAgent:
    """Query the indexed vibration library.

    Read-only by construction: every method reads FAISS indexes and chunk files
    that the ingestion pipeline wrote. There is no method here that can add,
    modify or remove a document.
    """

    def __init__(self, model_factory=None) -> None:
        """``model_factory`` is the test seam.

        It defaults to the app's ``get_chat_model`` but is injected rather than
        imported at module level, so a test can script a fake model without the
        package reaching for an API key at import time.
        """
        self._model_factory = model_factory

    def _chat_model(self, purpose: str = "agent"):
        if self._model_factory is not None:
            return self._model_factory(purpose)
        from app.llm.provider import get_chat_model

        return get_chat_model(purpose)

    def _plan(self, question: str, trace: list[dict[str, Any]]) -> list[str]:
        """Decompose the question into searches, before the model gets a say.

        Falls back to the raw question on any failure. A weaker set of searches
        still answers many questions; no searches answers none, so planning
        must never be able to fail the turn.
        """
        started = time.perf_counter()
        try:
            model = self._chat_model("classify").with_structured_output(SearchPlan)
            plan: SearchPlan = model.invoke(PLAN_PROMPT.format(question=question))
            queries = [q.strip() for q in plan.queries if q and q.strip()][:4]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Search planning failed, using the question verbatim: %s", exc)
            trace.append({"step": "plan searches", "detail": f"failed: {exc}"})
            return [question.strip()]

        if not queries:
            queries = [question.strip()]
        trace.append(
            {
                "step": "plan searches",
                "detail": " | ".join(queries),
                "ms": int((time.perf_counter() - started) * 1000),
            }
        )
        return queries

    # ------------------------------------------------------------ inventory --

    def documents(self) -> AgentResult:
        """Every document available to search."""
        try:
            docs = library.list_documents()
        except Exception as exc:  # noqa: BLE001
            return _fail("kb_documents", f"Could not read the document index: {exc}")

        return AgentResult(
            ok=True,
            kind="kb_documents",
            data=docs,
            meta={
                "count": len(docs),
                "total_chunks": sum(d["chunk_count"] for d in docs),
                "generated_at": _now(),
                "caveats": CAVEATS,
            },
        )

    # --------------------------------------------------------------- search --

    def search(
        self,
        query: str,
        doc_ids: list[str] | None = None,
        top_k: int = KB_TOP_K,
        chunk_types: list[str] | None = None,
    ) -> AgentResult:
        """Raw retrieval. No model is called, so this needs no API key.

        Useful on its own for checking whether a topic is in the corpus at all,
        and useful as the first thing to try when an answer looks wrong — if
        the passages are bad, the problem is retrieval, not reasoning.
        """
        if not query.strip():
            return _fail("kb_search", "Query is empty.")
        try:
            active = library.resolve_documents(doc_ids)
        except LookupError as exc:
            return _fail("kb_search", str(exc))
        if not active:
            return _fail(
                "kb_search",
                "No documents are indexed. Ingest one first: "
                "python scripts/ingest_folder.py <folder>",
            )

        started = time.perf_counter()
        try:
            hits = library.search(query, active, top_k, chunk_types)
        except Exception as exc:  # noqa: BLE001
            return _fail("kb_search", f"Search failed: {exc}")

        store = library.PassageStore(doc_ids=active)
        store.add(hits)
        passages = store.all_passages()

        return AgentResult(
            ok=True,
            kind="kb_search",
            data=[_public(p) for p in passages],
            meta={
                "query": query,
                "documents_searched": active,
                "chunk_types": chunk_types,
                "top_k": top_k,
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "generated_at": _now(),
                "caveats": CAVEATS,
            },
        )

    def passage(self, doc_id: str, chunk_id: str) -> AgentResult:
        """One passage in full, by id."""
        found = library.passage(doc_id, chunk_id)
        if not found:
            return _fail(
                "kb_passage",
                f"No passage {chunk_id} in document {doc_id}. "
                "Ids come from a search result.",
            )
        found["label"] = 1
        return AgentResult(
            ok=True,
            kind="kb_passage",
            data=[_public(found)],
            meta={
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "citation": library.cite(found),
                "generated_at": _now(),
                "caveats": CAVEATS,
            },
        )

    # ------------------------------------------------------------------ ask --

    def ask(
        self,
        question: str,
        doc_ids: list[str] | None = None,
        top_k: int = KB_TOP_K,
        max_iterations: int = KB_MAX_ITERATIONS,
    ) -> AgentResult:
        """Answer a question from the library, with citations.

        The model runs its own searches until it has enough, bounded by
        ``max_iterations``. Every passage it saw is returned in ``data``, so a
        caller can check a citation without re-running anything.
        """
        if not question.strip():
            return _fail("kb_answer", "Question is empty.")
        try:
            active = library.resolve_documents(doc_ids)
        except LookupError as exc:
            return _fail("kb_answer", str(exc))
        if not active:
            return _fail(
                "kb_answer",
                "No documents are indexed. Ingest one first: "
                "python scripts/ingest_folder.py <folder>",
            )

        store = library.PassageStore(doc_ids=active)
        tools = build_tools(store)
        by_name = {t.name: t for t in tools}
        trace: list[dict[str, Any]] = []
        started = time.perf_counter()

        try:
            model = self._chat_model("agent").bind_tools(tools)
        except Exception as exc:  # noqa: BLE001 — usually a missing API key
            return _fail("kb_answer", f"Could not build the chat model: {exc}")

        inventory = "\n".join(
            f"  {d['doc_id']}: {d['title']} ({d['chunk_count']} chunks)"
            for d in library.list_documents()
            if d["doc_id"] in active
        )

        # Authoritative limits go in before any search, so the model can never
        # be in the position of having only the document's incomplete tables.
        iso_fact = _forced_iso_lookup(question)
        iso_payload = iso_fact.pop("_payload", "") if iso_fact else ""
        if iso_fact is not None:
            store.add([iso_fact])
            trace.append({"step": "iso lookup", "detail": "authoritative limits injected"})

        planned_queries = self._plan(question, trace)
        for query in planned_queries:
            step = time.perf_counter()
            try:
                hits = library.search(query, active, top_k, None)
            except Exception as exc:  # noqa: BLE001 — one bad query must not end the turn
                logger.warning("Planned search failed for %r: %s", query[:60], exc)
                trace.append({"step": "planned search", "detail": f"{query} -> failed: {exc}"})
                continue
            if query.lower() not in {q.lower() for q in store.searches}:
                store.searches.append(query)
            store.add(hits)
            trace.append(
                {
                    "step": "planned search",
                    "detail": f"{query} -> {len(hits)} hits",
                    "ms": int((time.perf_counter() - step) * 1000),
                }
            )

        planned_block = (
            library.format_excerpts(store.best(KB_ANSWER_EXCERPTS), 500)
            if store.found
            else "(The planned searches returned nothing.)"
        )
        messages: list[Any] = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=SEARCH_PROMPT.format(
                    question=question, documents=inventory, planned=planned_block
                )
            ),
        ]

        iterations = 0
        for iterations in range(1, max_iterations + 1):
            step = time.perf_counter()
            try:
                response = model.invoke(messages)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Model call failed on iteration %d: %s", iterations, exc)
                # Everything found so far is still usable, so degrade to an
                # answer over those passages rather than losing the work.
                trace.append({"step": f"model call {iterations}", "detail": f"failed: {exc}"})
                break

            messages.append(response)
            calls = getattr(response, "tool_calls", None) or []
            trace.append(
                {
                    "step": f"model call {iterations}",
                    "detail": ", ".join(c.get("name", "?") for c in calls) or "no tool calls",
                    "ms": int((time.perf_counter() - step) * 1000),
                }
            )
            if not calls:
                break

            for call in calls:
                name = call.get("name", "")
                tool = by_name.get(name)
                if tool is None:
                    messages.append(
                        ToolMessage(content=f"Unknown tool: {name}", tool_call_id=call["id"])
                    )
                    continue
                tool_started = time.perf_counter()
                try:
                    content = tool.invoke(call.get("args") or {})
                except Exception as exc:  # noqa: BLE001 — a bad call must not end the turn
                    logger.warning("Tool %s failed: %s", name, exc)
                    content = json.dumps({"error": f"{name} failed: {exc}"})
                messages.append(ToolMessage(content=content, tool_call_id=call["id"]))
                trace.append(
                    {
                        "step": f"tool {name}",
                        "detail": str(call.get("args") or {})[:120],
                        "ms": int((time.perf_counter() - tool_started) * 1000),
                    }
                )

        # Selected by score, but PRESENTED in document order. A table's title
        # and its values are separate chunks; score order can put the values
        # above the title, or between two other tables, and then the model
        # cannot tell which table it is reading. ISO 10816-3 forced this:
        # two identically shaped zone tables, whose captions lost their
        # 'Table A.1 / Group 1' headings during rendering.
        excerpts = sorted(
            store.best(KB_ANSWER_EXCERPTS),
            key=lambda p: (p.get('doc_id', ''), int(p.get('page_start', 0) or 0),
                           p.get('chunk_id', '')),
        )
        if not excerpts:
            return AgentResult(
                ok=True,
                kind="kb_answer",
                data=[],
                meta={
                    "question": question,
                    "answer": (
                        "I could not find anything on this in the indexed documents. "
                        f"Searches run: {store.searches or 'none'}. Try naming the "
                        "phenomenon in textbook terms, or check that the relevant book "
                        "is indexed with `python -m kb_agent docs`."
                    ),
                    "documents_searched": active,
                    "searches_run": len(store.searches),
                    "searches": store.searches,
                    "iterations": iterations,
                    "grounded": False,
                    "trace": trace,
                    "elapsed_ms": int((time.perf_counter() - started) * 1000),
                    "generated_at": _now(),
                    "caveats": CAVEATS,
                },
            )

        answer_started = time.perf_counter()
        try:
            answer_model = self._chat_model("generate")
            final = answer_model.invoke(
                [
                    SystemMessage(content=SYSTEM_PROMPT),
                    HumanMessage(
                        content=ANSWER_PROMPT.format(
                            excerpts=library.format_excerpts(excerpts, KB_ANSWER_CHARS),
                            searches="; ".join(store.searches) or "none",
                            question=question,
                        )
                    ),
                ]
            )
            answer = (getattr(final, "content", "") or "").strip()
            block = _iso_answer_block(iso_payload) if iso_payload else ""
            if block:
                # Stated by code, above the prose. The model may explain these
                # figures; it did not choose them and cannot change them.
                answer = block + "\n\n" + answer
            answer, repaired = _enforce_verbatim_equations(answer, excerpts)
            if repaired:
                logger.info("Restored verbatim equation(s): %s", ", ".join(repaired))
            answer = _annotate_equations(answer, excerpts)
            answer, unsupported_std = _check_standard_attribution(answer, excerpts)
            if unsupported_std:
                logger.warning("Unsupported standard reference(s): %s", unsupported_std)
            answer = _flag_scoped_limits(answer, question)
        except Exception as exc:  # noqa: BLE001
            return _fail("kb_answer", f"Could not generate the answer: {exc}")

        trace.append(
            {
                "step": "write answer",
                "detail": f"{len(excerpts)} excerpts",
                "ms": int((time.perf_counter() - answer_started) * 1000),
            }
        )

        return AgentResult(
            ok=True,
            kind="kb_answer",
            data=[_public(p) for p in store.all_passages()],
            meta={
                "question": question,
                "answer": answer,
                "cited_labels": _cited(answer),
                "documents_searched": active,
                "searches": store.searches,
                "searches_run": len(store.searches),
                "iterations": iterations,
                "excerpts_used": len(excerpts),
                "trace": trace,
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "generated_at": _now(),
                "caveats": CAVEATS,
            },
        )


#: Appended when an answer reproduces an equation. Deliberately plain: the
#: reader needs to know the characters in front of them may be incomplete.
EQUATION_WARNING = (
    "Note: this equation is quoted exactly as PDF extraction produced it. "
    "Extraction drops fraction bars, division signs, minus signs and Greek "
    "letters, so operators may be missing -- check it against the cited page "
    "before using it."
)

#: Words that mean the answer already carries the warning in its own wording.
_WARNED = (
    "extraction", "extracted", "may have dropped", "operator", "verify",
    "check it against", "against the page", "as it appears", "missing",
)


#: "BPFO = NbSsh 2 ( 1  db Dp cos )" -- a name, an equals sign, and a run of
#: symbols. Loose on purpose: the point is to find what the answer PRESENTS as
#: an equation, whatever shape extraction left it in.
_EQUATION_RE = re.compile(r"([A-Za-z][A-Za-z0-9_]{1,12})\s*=\s*([^.\n\[]{6,120})")


def _enforce_verbatim_equations(
    answer: str, excerpts: list[dict[str, Any]]
) -> tuple[str, list[str]]:
    """Replace any equation the model rewrote with the source's own characters.

    Measured over five runs, the model quoted the damaged BPFO equation
    unaltered twice and "helpfully" repaired it three times -- inserting the
    fraction bar and minus sign that extraction had destroyed, while dropping
    the divide-by-two, which doubles every value computed from it. A prompt
    rule forbidding this has been in place for several runs and does not hold.

    So the guarantee moves into code. For every ``NAME = ...`` the answer
    presents, if a cited excerpt contains the same left-hand side, the
    right-hand side is replaced with the excerpt's, character for character.
    The model may still choose which equation to quote; it may no longer
    choose what the equation says.
    """
    if not answer:
        return answer, []
    sources: dict[str, str] = {}
    for excerpt in excerpts:
        for name, body in _EQUATION_RE.findall(excerpt.get("text") or ""):
            sources.setdefault(name.upper(), _trim_equation(body))

    corrected: list[str] = []

    def repair(match: re.Match) -> str:
        name, body = match.group(1), match.group(2)
        truth = sources.get(name.upper())
        if truth is None or _same_equation(body, truth):
            return match.group(0)
        corrected.append(name.upper())
        return f"{name} = {truth}"

    return _EQUATION_RE.sub(repair, answer), sorted(set(corrected))


#: A trailing "(2.12)" is the equation's number in the book, not part of it.
#: The closing paren is optional because _EQUATION_RE stops at the first ".",
#: so the captured tail is the fragment "(2" rather than the whole label.
_EQ_LABEL_RE = re.compile(r"\s*\(\d+(?:\.\d+)*\)?\s*$")


def _trim_equation(body: str) -> str:
    return _EQ_LABEL_RE.sub("", (body or "").strip()).strip()


def _same_equation(a: str, b: str) -> bool:
    """Equal ignoring whitespace, citation markers and the equation number.

    Extraction leaves runs of spaces where operators used to be, so an exact
    string test would rewrite a correct quotation and report it as a repair.
    """
    def norm(text: str) -> str:
        text = re.sub(r"\[\d{1,2}\]", " ", text or "")
        return " ".join(_trim_equation(text).split())

    return norm(a) == norm(b)


#: "ISO 10816-3", "API 610", "IEC 60034-14" -- a body plus a part number. The
#: number is the whole point: API 610 covers centrifugal pumps, 617 covers
#: compressors, 611 covers steam turbines, and their limits differ.
_STANDARD_RE = re.compile(
    r"\b(ISO|API|IEC|ANSI|BS|DIN|ASTM|AGMA|NEMA)\s*[-\s]?(\d{2,5}(?:[.-]\d+)*)",
    re.IGNORECASE,
)


def _check_standard_attribution(
    answer: str, excerpts: list[dict[str, Any]]
) -> tuple[str, list[str]]:
    """Flag a standard's number that no cited excerpt actually states.

    Observed: a passage reading "The API specification on vibration limits for
    turbo machines... the API standard specifies..." was reported as "API 610
    specifies ... for centrifugal pumps". The source names neither the part
    number nor the machine type; both came from the question. "API 610" does
    not appear anywhere in the corpus.

    That is the failure this rule exists for. A part number is not decoration --
    it selects which limits apply -- and a reader has no way to tell an
    attributed number from a quoted one. The prompt has forbidden this for
    several runs and it still happened, so it is checked here instead.
    """
    if not answer:
        return answer, []
    haystack = " ".join(e.get("text", "") for e in excerpts).lower()
    unsupported: list[str] = []
    for body, number in _STANDARD_RE.findall(answer):
        ref = f"{body.upper()} {number}"
        # Accept any spacing or punctuation the source happens to use.
        variants = (f"{body}{number}", f"{body} {number}", f"{body}-{number}")
        if not any(v.lower() in haystack for v in variants):
            unsupported.append(ref)
    if not unsupported:
        return answer, []
    named = ", ".join(sorted(set(unsupported)))
    warning = (
        f"WARNING -- this answer names {named}, but no cited passage states that "
        "number. The sources may refer to the body generally (\"the API standard\") "
        "without saying which part. Part numbers select which limits apply, so treat "
        "the attribution as unverified and check the cited page."
    )
    return f"{answer.rstrip()}\n\n{warning}", sorted(set(unsupported))


#: A severity limit quoted for a specific machine: "... is 2.8 mm/s".
_LIMIT_RE = re.compile(r"\b\d+[.,]\d+\s*mm\s*/\s*s", re.IGNORECASE)
#: The question pins a machine to a table row by its rating.
_RATING_RE = re.compile(r"\b\d+(?:[.,]\d+)?\s*(kW|MW|hp)\b", re.IGNORECASE)

SCOPED_LIMIT_WARNING = (
    "Note: selecting the right row of a standards severity table -- the right "
    "machine group, support class and column -- is NOT reliable from this "
    "agent. Measured over five runs of one question it chose correctly once. "
    "The number above may be from the wrong group or the wrong column. Confirm "
    "it with the deterministic tool, which is unit-tested against the published "
    "values:\n"
    "    python scripts/vib_cli.py iso --vrms <value> --power-kw <kW> "
    "--type <machine> --foundation <rigid|flexible>"
)


def _flag_scoped_limits(answer: str, question: str) -> str:
    """Warn whenever a machine-specific severity limit is stated.

    Unlike the equation guard, this cannot be made correct in code: there is no
    single true string to substitute, only a row that has to be chosen. The
    choice was measured at 1/5 -- worse than a coin, and a vibration limit that
    is wrong 80% of the time while reading as authoritative is the most
    dangerous output this agent can produce.

    So the guarantee here is not correctness but disclosure: any answer that
    pins a limit to a rated machine carries a pointer to the tool that gets it
    right. This project's own rule is that an LLM never supplies a number;
    app/domain/iso10816.py is where this number belongs.
    """
    if not answer or not _RATING_RE.search(question or ""):
        return answer
    if not _LIMIT_RE.search(answer):
        return answer
    if "vib_cli" in answer:
        return answer
    return f"{answer.rstrip()}\n\n{SCOPED_LIMIT_WARNING}"


def _annotate_equations(answer: str, excerpts: list[dict[str, Any]]) -> str:
    """Append the extraction caveat when an answer reproduces an equation.

    The system prompt already asks the model to say this, and the model does
    not do it reliably -- the evaluation caught an answer that quoted
    "BPFO = NbSsh 2 ( 1  db Dp cos )" perfectly and then let it stand as if
    complete. Quoting a damaged equation without saying it is damaged is only
    half safe, so the guarantee is moved into code, where compliance is not
    optional.

    Detection is conservative: the answer must reproduce a run of characters
    that appears verbatim in a cited excerpt AND contains "=". Prose about a
    formula does not trigger it; a reproduced formula does.
    """
    if not answer or any(w in answer.lower() for w in _WARNED):
        return answer
    for line in answer.splitlines():
        if "=" not in line:
            continue
        for excerpt in excerpts:
            text = excerpt.get("text") or ""
            # Slide a window over the line looking for a shared run.
            for size in (24, 18, 14):
                for start in range(0, max(1, len(line) - size + 1)):
                    fragment = line[start : start + size]
                    if "=" in fragment and fragment in text:
                        return f"{answer.rstrip()}\n\n{EQUATION_WARNING}"
    return answer


def _public(p: dict[str, Any]) -> dict[str, Any]:
    """The passage shape a caller sees. Full text included — this is evidence."""
    return {
        "label": p.get("label"),
        "doc_id": p.get("doc_id", ""),
        "chunk_id": p.get("chunk_id", ""),
        "chunk_type": p.get("chunk_type", "clause"),
        "section_path": p.get("section_path", ""),
        "page_start": p.get("page_start", 0),
        "page_end": p.get("page_end", 0),
        "score": round(float(p.get("score", 0.0)), 4),
        "citation": library.cite(p),
        "text": p.get("text", ""),
    }


def _cited(answer: str) -> list[int]:
    """Which excerpt labels the answer actually cited.

    A cheap groundedness signal: an answer with prose but no citations was
    written from the model's own knowledge, whatever the prompt said.
    """
    import re

    return sorted({int(n) for n in re.findall(r"\[(\d{1,2})\]", answer or "")})


#: Module-level instance, matching sql_agent's ``sensor_agent``.
kb_agent = KnowledgeBaseAgent()
