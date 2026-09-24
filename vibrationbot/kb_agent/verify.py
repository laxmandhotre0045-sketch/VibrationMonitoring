"""A verification sheet: every claim, beside the book text it came from.

The agent already prints citations. A citation tells you *where* a claim came
from; it does not let you check *whether the source says it*. Doing that by
hand means running ``passage`` for each id, matching it back to the right
sentence, and holding both in your head. This does that work for you.

For each sentence of the answer it prints the sentence, the exact untruncated
passage behind it, and the PDF page to open if you want to see it on the page
itself. Three things are then checkable by eye, with no tooling and no trust in
the agent:

* Does the source actually say what the claim says?
* Is the claim about the same subject as the passage?
* Is there any sentence with no source at all?

That last one matters most. A sentence carrying no citation was not taken from
the books, whatever the rest of the answer looks like, and it is listed first
and separately for exactly that reason.

The word-overlap percentage is a hint for where to look first, never a verdict.
A correct paraphrase can score low and a wrong claim can score high; only
reading the two together settles it.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.config import DOCUMENTS_DIR

CITE_RE = re.compile(r"\[(\d{1,2})\]")
#: Split on sentence ends and bullet starts -- an answer is bullets, and each
#: bullet is one claim by construction (the system prompt requires it).
CLAIM_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])|\n\s*[-*]\s*")

#: A sentence stating what the sources do NOT say is a disclaimer, not a claim
#: about vibration, and needs no citation of its own.
_DISCLAIMER_RE = re.compile(
    r"\b(excerpts? do(es)? not|do(es)? not (provide|specify|state|include|mention|detail)|"
    r"not (provided|specified|stated|included|mentioned|detailed|found|available)|"
    r"could not find|no (further |additional )?(excerpts?|information)|"
    r"for (a )?more (precise|targeted)|consider searching)\b",
    re.IGNORECASE,
)

STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "of", "in",
    "for", "on", "with", "at", "by", "from", "as", "to", "and", "or", "but",
    "that", "this", "these", "those", "it", "its", "which", "when", "while",
    "can", "will", "may", "also", "such", "than", "then", "there", "their",
    "not", "no", "any", "all", "more", "most", "other", "into", "about",
}


def _ascii(text: str) -> str:
    return (text or "").encode("ascii", "ignore").decode("ascii")


def _words(text: str) -> set[str]:
    return {
        w for w in re.findall(r"[a-z]+", _ascii(text).lower())
        if len(w) > 2 and w not in STOPWORDS
    }


def _overlap(claim: str, source: str) -> int:
    claim_words = _words(claim)
    if not claim_words:
        return 0
    return round(100 * len(claim_words & _words(source)) / len(claim_words))


def _wrap(text: str, width: int, indent: str) -> str:
    import textwrap

    out: list[str] = []
    for para in _ascii(text).split("\n"):
        if not para.strip():
            continue
        out.extend(
            textwrap.wrap(para.strip(), width=width,
                          initial_indent=indent, subsequent_indent=indent)
        )
    return "\n".join(out)


def _source_pdf(doc_id: str) -> str:
    for candidate in sorted((DOCUMENTS_DIR / doc_id).glob("source.*")):
        return str(Path(*candidate.parts[-4:]))
    return f"data/documents/{doc_id}/source.*"


def claims_with_citations(answer: str) -> list[tuple[str, list[int]]]:
    """Split an answer into claims, each with the labels it cites."""
    claims: list[tuple[str, list[int]]] = []
    for piece in CLAIM_SPLIT_RE.split(answer or ""):
        text = " ".join((piece or "").split())
        if len(text) < 25:
            continue
        claims.append((text, sorted({int(n) for n in CITE_RE.findall(text)})))
    return claims


def build_report(result, width: int = 96) -> str:
    """The full verification sheet for one AgentResult."""
    meta = result.meta
    answer = meta.get("answer", "")
    by_label = {int(s["label"]): s for s in result.data if s.get("label") is not None}
    claims = claims_with_citations(answer)
    # An uncited sentence is only alarming if it ASSERTS something the sources
    # do not carry. Two kinds legitimately carry no [n]: the opening sentence,
    # which summarises the cited bullets below it, and the closing disclaimer,
    # which states what the excerpts did NOT contain. Flagging those trains the
    # reader to ignore the alarm, and the alarm is the whole point of the page.
    cited_text = " ".join(
        s.get("text", "") for s in result.data
        if s.get("label") in {int(n) for n in CITE_RE.findall(answer or "")}
    )
    uncited: list[str] = []
    summarising: list[str] = []
    for claim, labels in claims:
        if labels:
            continue
        if _DISCLAIMER_RE.search(claim):
            continue
        if cited_text and _overlap(claim, cited_text) >= 40:
            summarising.append(claim)
        else:
            uncited.append(claim)

    out: list[str] = []
    rule = "=" * width
    out.append(rule)
    out.append("  VERIFICATION SHEET")
    out.append(rule)
    out.append(_wrap(f"Question: {meta.get('question','')}", width, "  "))
    out.append("")
    out.append(
        _wrap(
            "Read each claim against the book text printed beneath it. The PDF page is "
            "given so you can confirm it on the page itself.",
            width - 2,
            "  ",
        )
    )
    out.append("")

    # -- the part that matters most, first --------------------------------
    out.append("-" * width)
    if uncited:
        out.append(f"  {len(uncited)} CLAIM(S) WITH NO SOURCE -- these were not taken from the books")
        out.append("-" * width)
        for claim in uncited:
            out.append(_wrap(claim, width - 6, "    ! "))
            out.append("")
    else:
        out.append("  No unsourced claim. Every assertion below traces to a passage.")
        out.append("-" * width)
    if summarising:
        out.append("")
        out.append("  (Uncited, but only restating what the cited passages below say --")
        out.append("   the opening summary and similar. Check them against the claims.)")
        for claim in summarising:
            out.append(_wrap(claim, width - 8, "      ~ "))
    out.append("")

    for index, (claim, labels) in enumerate(
        [(c, l) for c, l in claims if l], start=1
    ):
        out.append("-" * width)
        out.append(f"  CLAIM {index}")
        out.append(_wrap(claim, width - 4, "    "))
        out.append("")
        for label in labels:
            source = by_label.get(label)
            if source is None:
                out.append(f"    [{label}]  *** NO SUCH EXCERPT WAS RETRIEVED -- invented reference ***")
                out.append("")
                continue
            doc_id = source.get("doc_id", "")
            page = source.get("page_start", 0)
            score = _overlap(claim, source.get("text", ""))
            strength = "strong" if score >= 45 else ("partial" if score >= 20 else "WEAK - read closely")
            out.append(f"    SOURCE [{label}]   word overlap {score}%  ({strength})")
            out.append(f"      where : {_ascii(source.get('citation',''))}")
            out.append(f"      open  : {_source_pdf(doc_id)}   at PDF page {page}")
            out.append("      the book says:")
            out.append("      " + "." * (width - 8))
            out.append(_wrap(source.get("text", ""), width - 10, "      | "))
            out.append("      " + "." * (width - 8))
            out.append("")

    out.append(rule)
    out.append(f"  {len(claims)} claim(s), {len(uncited)} unsourced, "
               f"{len(by_label)} excerpt(s) retrieved, "
               f"{len(meta.get('searches') or [])} search(es) run")
    out.append("  Anything above marked WEAK or unsourced is where to look first.")
    out.append(rule)
    return "\n".join(out)
