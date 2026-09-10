"""
Clean section_path values for citation display -> chunks_sanitized.jsonl.

The original version only normalised whitespace and collapsed adjacent
duplicates. That was not enough: measured against the two ingested books, 95%
of ``cat2`` chunks carried the running page header "MOBIUS INSTITUTE" as their
top-level "chapter", 96% of ``condition_monitoring`` carried the stray figure
label "NA4*", and roughly half of every document ended its path with a segment
that merely repeated the first 80 characters of the chunk's own body text.

The cause is upstream, in ``document_pdf_pipeline._is_heading``: any all-caps
line of twelve words or fewer counts as a heading, so a running header becomes
a chapter and never gets replaced, and clause titles are built as ``body[:80]``.
That is fixed there for future ingests, but the damage is baked into every
chunk already on disk, and re-extracting costs a full re-ingest.

So this pass repairs rather than merely normalises, and it is corpus-aware: it
reads the whole document first, decides which segments are page furniture by
how often they repeat, and only then rewrites. Three rules:

* A segment appearing on more than ``HEADER_SHARE`` of a document's chunks is
  page furniture, not structure. A real chapter title covers a slice of a book;
  a running header covers all of it.
* A trailing segment that restates the beginning of the chunk's own text is the
  ``body[:80]`` artefact, and carries nothing a reader cannot already see.
* Copyright lines, "all rights reserved" and printer credits are boilerplate
  wherever they appear.

What survives is often nothing, and that is the honest result. Rather than
print noise, the path falls back to the chapter number, which *is* recoverable:
chapter openers are letter-spaced ("C H A P T E R 1 1"), so the number can be
read even though the title's word boundaries cannot -- "D I A G N O S I N G M I
S A L I G N M E N T" separates its words with the same single space it puts
between letters, so no de-spacing can tell where one word ends. Chapters found
this way are propagated forward by page, giving every chunk between two
chapter openers the earlier one's number.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

MULTI_SPACE_RE = re.compile(r"\s+")
SEPARATOR_RE = re.compile(r"\s*>\s*")
REDUNDANT_RE = re.compile(r"^(CHAPTER|SECTION)\s+\d+\s*>\s*", re.IGNORECASE)

#: A segment on more than this share of a document's chunks is page furniture.
#: Chapter titles in these books cover 3-8% of a document each; the observed
#: running headers cover 95-96%. Anything above a third is not structure.
#: Lowered from 0.33 after a scanned book put its publisher's city list
#: ("SAN FRANCISCO SINGAPORE SYDNEY TOKYO") on 23% of chunks -- front matter
#: repeated through the document, under the old threshold. Real chapter titles
#: in these books cover 3-8% of a document each, so a fifth is still a wide
#: margin above anything genuine.
HEADER_SHARE = 0.20

#: Publisher furniture that is never structure, matched case-insensitively.
BOILERPLATE_RE = re.compile(
    r"all rights reserved|copyright|\(c\)\s*\d{4}|\d{4}\s*-\s*\d{4}|"
    r"produced by|www\.|edition .*published|john wiley|do not copy",
    re.IGNORECASE,
)

#: Upper bounds for a real heading. Chapter and section titles in these books
#: run two or three words; anything longer is the ``body[:80]`` clause title,
#: which often carries the page's running header in front of it and so escapes
#: the "restates the body" test.
MAX_TITLE_WORDS = 8
MAX_TITLE_CHARS = 60

#: "C H A P T E R 1 1" or "CHAPTER 11". The letters may be split by single
#: spaces, so the pattern allows an optional space after each one.
CHAPTER_RE = re.compile(
    r"C\s?H\s?A\s?P\s?T\s?E\s?R\s+([0-9]\s?[0-9]?)", re.IGNORECASE
)

#: How far into a chunk a chapter opener may appear. Openers sit at the very
#: top of a page; a "chapter" mentioned mid-paragraph is a cross-reference.
CHAPTER_SCAN_CHARS = 120

#: Labels the pipeline itself assigns to non-prose chunks. These are real, and
#: they are single words, so they must bypass the title test below.
PIPELINE_LABELS = {"figures", "figure", "tables", "table"}

#: Measurement and citation debris. A "heading" containing an operating point
#: ("400 GPM @ 112 head"), a rating ("300 HP motor", "18 - 30V") or a journal
#: reference is body text the heading detector mistook for structure.
NOT_A_TITLE_RE = re.compile(
    r"\d\s*(hz|v|hp|kw|gpm|rpm|psi|mm|in|deg|%)\b|"
    r"@|\bieee\b|\bconference\b|\bproceedings\b|\bvol\.|\bpp\.",
    re.IGNORECASE,
)


def looks_like_title(segment: str) -> bool:
    """Is this segment plausibly a real heading rather than stray body text?

    Deliberately strict. Every segment these two books produced failed one of
    these tests, which is the finding that drove the rewrite: the extraction
    recovered no section structure at all, so admitting a segment "just in
    case" only prints noise beside a citation and invites a reader to trust it.
    """
    seg = segment.strip()
    if seg.lower() in PIPELINE_LABELS:
        return True
    words = seg.split()
    if not (2 <= len(words) <= MAX_TITLE_WORDS) or len(seg) > MAX_TITLE_CHARS:
        return False
    if NOT_A_TITLE_RE.search(seg):
        return False
    # Prose, not a title: a sentence break, or a mid-string full stop.
    if re.search(r"\.\s+\S|\.\s*$", seg) and seg.lower() not in PIPELINE_LABELS:
        return False
    letters = sum(c.isalpha() for c in seg)
    digits = sum(c.isdigit() for c in seg)
    if letters < 0.6 * len(seg) or digits > 0.15 * len(seg):
        return False
    if _looks_ocr_damaged(seg):
        return False
    return True


#: Characters OCR emits when it cannot read a glyph, and that no real heading
#: contains. A scanned bearing textbook produced "ROLLI~G B" and "BEARING
#: LOADS ANL) SPEEDS" as chapter titles this way.
_OCR_NOISE_RE = re.compile(r"[~|^_\\<>{}]|\)\s*[A-Z]|[A-Za-z]\)")


def _looks_ocr_damaged(segment: str) -> bool:
    """Is this heading a mis-scan rather than words?

    Two signals, both taken from real output. Stray symbols in the middle of
    letters mean the scanner guessed. And a trailing one- or two-letter word in
    an otherwise capitalised run is a word the page cut off -- "ROLLING E",
    "ROLLI~G B" -- which is a fragment of a title, not a title.
    """
    if _OCR_NOISE_RE.search(segment):
        return True
    # A heading does not end mid-thought. A trailing hyphen, comma or slash is
    # a fragment the page cut off -- "1 Revolution -" is an axis label.
    if segment.rstrip().endswith(("-", ",", "/", ":", ";", "+")):
        return True
    words = segment.split()
    if segment.upper() == segment:
        # An all-caps run carrying a stray one- or two-letter word is a title
        # the scanner sliced: "ROLLING E", "G INTE", "ROLLI~G B".
        if any(w.isalpha() and len(w) <= 2 for w in words):
            return True
    return False


def sanitize_section_path(path: str) -> str:
    """Normalise one path. Kept for callers that have no document context."""
    if not path:
        return "Unknown Section"
    cleaned = MULTI_SPACE_RE.sub(" ", path.strip())
    parts = [p.strip() for p in SEPARATOR_RE.split(cleaned) if p.strip()]
    deduped: list[str] = []
    for part in parts:
        if not deduped or deduped[-1].lower() != part.lower():
            deduped.append(part)
    result = " > ".join(deduped)
    result = REDUNDANT_RE.sub("", result).strip()
    return result or "Unknown Section"


def _segments(path: str) -> list[str]:
    cleaned = MULTI_SPACE_RE.sub(" ", (path or "").strip())
    return [p.strip() for p in SEPARATOR_RE.split(cleaned) if p.strip()]


def find_chapter(text: str) -> str | None:
    """Chapter number from a letter-spaced opener at the head of a chunk."""
    match = CHAPTER_RE.search((text or "")[:CHAPTER_SCAN_CHARS])
    if not match:
        return None
    number = match.group(1).replace(" ", "")
    return number if number.isdigit() else None


def _restates_body(segment: str, text: str) -> bool:
    """Is this segment just the opening of the chunk's own text?

    Compared with spaces removed: the ``body[:80]`` title is cut mid-word and
    the letter-spaced headers make a literal prefix test unreliable.
    """
    seg = re.sub(r"\W+", "", segment).lower()[:40]
    body = re.sub(r"\W+", "", text or "").lower()[:120]
    return len(seg) >= 12 and seg in body


def sanitize_chunks(input_path: Path, output_path: Path) -> int:
    """Repair every section_path in one document. Returns the chunk count."""
    chunks: list[dict] = []
    with input_path.open(encoding="utf-8") as fin:
        for line in fin:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    if not chunks:
        output_path.write_text("", encoding="utf-8")
        return 0

    # Pass 1 -- how often does each segment appear, and where do chapters start?
    frequency: Counter[str] = Counter()
    for chunk in chunks:
        for segment in set(s.lower() for s in _segments(chunk.get("section_path", ""))):
            frequency[segment] += 1

    limit = max(2, int(len(chunks) * HEADER_SHARE))
    furniture = {seg for seg, count in frequency.items() if count > limit}

    chapter_at_page: dict[int, str] = {}
    for chunk in chunks:
        number = find_chapter(chunk.get("text", ""))
        if number:
            page = int(chunk.get("page_start", 0) or 0)
            chapter_at_page.setdefault(page, number)

    # Pass 2 -- rewrite, then carry the last seen chapter forward by page.
    ordered_pages = sorted(chapter_at_page)
    with output_path.open("w", encoding="utf-8") as fout:
        for chunk in chunks:
            text = chunk.get("text", "")
            kept = [
                seg
                for seg in _segments(chunk.get("section_path", ""))
                if seg.lower() not in furniture
                and not BOILERPLATE_RE.search(seg)
                and not _restates_body(seg, text)
                and looks_like_title(seg)
            ]

            # The chapter leads when one is known: it is derived from the
            # book's own printed opener and propagated by page, which is the
            # only structural signal in this data that survived extraction.
            page = int(chunk.get("page_start", 0) or 0)
            number = None
            for start in ordered_pages:
                if start <= page:
                    number = chapter_at_page[start]
                else:
                    break
            # Deduplicate case-insensitively, and drop a derived "Chapter 8"
            # when a kept segment already names that chapter more fully
            # ("Chapter 8 - Statically Loaded Bearings"). Without this the
            # DSP guide rendered "Chapter 32- The Laplace Transform > Chapter
            # 32- The Laplace Transform".
            parts: list[str] = []
            for candidate in ([f"Chapter {number}"] if number else []) + kept:
                lower = candidate.lower()
                if any(lower == p.lower() or lower in p.lower() for p in parts):
                    continue
                parts = [p for p in parts if p.lower() not in lower] + [candidate]
            path = REDUNDANT_RE.sub("", " > ".join(parts)).strip()

            chunk["section_path"] = path or "Unknown Section"
            fout.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    return len(chunks)
