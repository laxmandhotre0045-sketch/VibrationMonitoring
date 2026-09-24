"""
Remove TOC noise and short chunks from chunks.jsonl → chunks_clean.jsonl.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

TOC_LINE_RE = re.compile(r"\.{3,}\s*\d+\s*$")
TOC_KEYWORD_RE = re.compile(
    r"\b(table of contents|contents|index)\b",
    re.IGNORECASE,
)
PAGE_ONLY_RE = re.compile(r"^\s*\d+\s*$")


#: The caption model sometimes replies to an image with a refusal -- "I'm
#: unable to view images directly. However, if you provide the text..." -- and
#: the pipeline stored that as page content. Ten such chunks reached the index
#: across three documents before this was caught: retrievable, citable, and
#: saying nothing about vibration.
VISION_REFUSAL_RE = re.compile(
    r"\b(i'?m unable to|i am unable to|i cannot view|i can'?t view|"
    r"it seems that i (cannot|can'?t)|unable to view images|"
    r"unable to identify or describe|if you (can )?(provide|describe|share) the)\b",
    re.IGNORECASE,
)


def is_vision_refusal(text: str) -> bool:
    """Is this the caption model declining, rather than page content?"""
    return bool(VISION_REFUSAL_RE.search((text or "")[:400]))


def _is_toc_chunk(text: str, section_path: str) -> bool:
    combined = f"{section_path} {text}"
    if TOC_KEYWORD_RE.search(combined) and len(text) < 200:
        return True
    lines = text.splitlines()
    toc_lines = sum(1 for ln in lines if TOC_LINE_RE.search(ln.strip()))
    if lines and toc_lines / len(lines) > 0.4:
        return True
    if PAGE_ONLY_RE.match(text.strip()):
        return True
    return False


def filter_chunks(
    input_path: Path,
    output_path: Path,
    min_chars: int = 40,
) -> int:
    kept = 0
    with input_path.open(encoding="utf-8") as fin, output_path.open(
        "w", encoding="utf-8"
    ) as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            chunk = json.loads(line)
            text = (chunk.get("text") or "").strip()
            section_path = chunk.get("section_path") or ""
            if len(text) < min_chars:
                continue
            if _is_toc_chunk(text, section_path):
                continue
            if is_vision_refusal(text):
                continue
            fout.write(json.dumps(chunk, ensure_ascii=False) + "\n")
            kept += 1
    return kept
