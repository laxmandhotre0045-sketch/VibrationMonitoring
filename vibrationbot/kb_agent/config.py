"""Settings for the knowledge-base agent.

Unlike ``sql_agent.config``, this package does NOT stand alone. The knowledge
base *is* the chatbot's retrieval stack — the same FAISS indexes, the same
BGE embeddings, the same cross-encoder rerank — so this agent imports
``app.retrieval`` rather than reimplementing search. Forking retrieval would
give two agents two different answers from one corpus, which is worse than the
extra dependency.

What is standalone is the reasoning on top: the tool loop, the prompts and the
answer contract live here, so they can be changed without touching the chatbot.
"""

from __future__ import annotations

import os as _os
from pathlib import Path as _Path

#: vibrationbot/ — this file is kb_agent/config.py, so two parents up.
BASE_DIR = _Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv as _load_dotenv

    _load_dotenv(BASE_DIR / ".env", override=False)
except ImportError:  # pragma: no cover — dotenv is optional for library use
    pass


def _int(name: str, default: int) -> int:
    try:
        return int(_os.getenv(name, str(default)))
    except ValueError:
        return default


#: Excerpts returned per search. Six is the chatbot's default and is tuned to
#: the reranker: raising it past ~10 admits passages the cross-encoder already
#: ranked as weak, which dilutes the answer rather than enriching it.
KB_TOP_K = _int("KB_TOP_K", 6)

#: Hard bound on the tool loop. Each iteration is one model call plus its
#: searches, so this is the cost ceiling for a single question. Four is enough
#: for the worst legitimate path — a broad search, a narrowing search, a table
#: lookup, and a passage fetch — without letting a confused model spin.
KB_MAX_ITERATIONS = _int("KB_MAX_ITERATIONS", 4)

#: Characters of each excerpt handed to the model. Full passages run to several
#: thousand characters; six of those per search across four iterations would
#: exhaust the context on text the model mostly skims. The full text is always
#: kept in the passage store and reaches the answer prompt intact.
KB_SNIPPET_CHARS = _int("KB_SNIPPET_CHARS", 700)

#: Characters per excerpt in the final answer prompt, where the model is
#: actually writing from the evidence and needs more of it.
KB_ANSWER_CHARS = _int("KB_ANSWER_CHARS", 1800)

#: Excerpts carried into the answer prompt, best-scoring first.
KB_ANSWER_EXCERPTS = _int("KB_ANSWER_EXCERPTS", 10)

#: Restated on every result so a consumer that never read this module still
#: gets them. Cheap to carry, expensive to omit.
CAVEATS = [
    "Answers are drawn only from the indexed documents. The corpus is not "
    "complete coverage of vibration practice — a topic absent from these "
    "books returns 'not found', which is not evidence that the topic is "
    "unimportant or that the answer is no.",
    "Page numbers are the page of the source PDF as ingested, which may differ "
    "from the printed page number in a scanned book's own numbering.",
    "Figure and table content was captioned into prose by a vision model at "
    "ingest time. A caption is a reading of the figure, not the figure itself; "
    "verify any value taken from a chart against the page.",
    "ISO 7919 and ISO 10816/20816 are not interchangeable, and this corpus "
    "carries the zone A/B/C/D wording only in its ISO 7919 passage (Cat2 "
    "chapter 19, PDF pp.564-565). ISO 7919 evaluates vibration measured ON THE "
    "SHAFT with proximity probes; ISO 10816/20816 evaluates vibration measured "
    "on NON-ROTATING PARTS such as bearing housings, which is what this "
    "platform's sensors and its iso10816 tools use. The zone letters read "
    "almost identically and the limits do not transfer. The corpus does "
    "discuss ISO 10816 (Cat2 chapter 19, PDF pp.558-562), but its zone "
    "boundaries live in figures rather than text, so they are not quotable "
    "here -- use the separate iso_agent for an actual zone.",
    "Displayed equations were largely lost at PDF extraction. In the Mobius "
    "Cat 2 material they survive as empty brackets such as '[ ( ) ( )]', and "
    "the surrounding prose still says 'using the formula below'. Ask this "
    "agent what a quantity MEANS and what inputs it needs; do not ask it to "
    "quote a formula, and never treat a missing equation as evidence that the "
    "source lacks one.",
    "This agent retrieves and explains. It performs no vibration calculation — "
    "bearing frequencies, ISO zones and unit conversions come from the "
    "deterministic tools in app/domain, not from here.",
]
