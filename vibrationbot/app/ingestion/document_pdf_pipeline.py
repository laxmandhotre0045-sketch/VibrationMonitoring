"""
PDF extraction, structure detection, and chunking for documents.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import fitz  # pymupdf

from app.config import PDF_TABLE_PARALLEL_MIN_PAGES, PDF_TABLE_WORKERS

logger = logging.getLogger(__name__)

HEADING_RE = re.compile(
    r"^(CHAPTER\s+\d+|SECTION\s+\d+|\d+(\.\d+)*\.?\s+[A-Z].{2,}|[A-Z][A-Z0-9\s\-]{4,})$"
)
CHAPTER_RE = re.compile(r"^CHAPTER\s+(\d+)", re.IGNORECASE)
SECTION_RE = re.compile(r"^SECTION\s+(\d+)", re.IGNORECASE)
NUMBERED_HEADING_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+(.+)$")


@dataclass
class StructuredNode:
    node_id: str
    node_type: str
    title: str
    page_start: int
    page_end: int
    section_path: str
    text: str = ""
    children: list[str] = field(default_factory=list)
    parent_id: str | None = None


from app.ingestion.sanitize_section_path import looks_like_title


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower())
    return slug.strip("_")[:60] or "node"


#: Share of pages a line must appear on to be treated as a running header or
#: footer rather than a heading. Measured on the two ingested books, the
#: publisher's page furniture ("MOBIUS INSTITUTE", "NA4*") appeared on
#: essentially every page while no real heading exceeded a few percent.
RUNNING_LINE_SHARE = 0.30


def _running_lines(pages: list[dict[str, Any]]) -> set[str]:
    """Lines repeated across most pages: headers, footers, watermarks.

    Without this the first such line became the document's chapter and, since
    nothing ever replaced it, stayed the top of every section_path for the
    whole book -- 95% of one book's chunks were filed under "MOBIUS INSTITUTE".
    """
    if not pages:
        return set()
    seen: dict[str, int] = {}
    for page in pages:
        for line in {ln.strip() for ln in (page.get("text") or "").splitlines() if ln.strip()}:
            seen[line] = seen.get(line, 0) + 1
    threshold = max(3, int(len(pages) * RUNNING_LINE_SHARE))
    return {line for line, count in seen.items() if count >= threshold}


def _is_heading(line: str, running: set[str] | None = None) -> bool:
    """Does this line open a section?

    The all-caps branch used to accept any line of twelve words or fewer, which
    is how page furniture and watermarks ("DO NOT COPY OR") became chapters.
    It now also has to look like a title: a few words, mostly letters, and free
    of the measurement debris that fills these books' figure callouts
    ("400 GPM @ 112' head", "18 - 30V", "300 HP motor").
    """
    line = line.strip()
    if len(line) < 4 or len(line) > 120:
        return False
    if running and line in running:
        return False
    # An explicit "CHAPTER 11" / "SECTION 4" says what it is; nothing else does.
    if CHAPTER_RE.match(line) or SECTION_RE.match(line):
        return True
    # Everything else -- the generic all-caps run and the numbered form -- has
    # to earn it. HEADING_RE's `[A-Z][A-Z0-9\s\-]{4,}` alternative matches any
    # capitalised fragment, and its numbered alternative matches "300 HP
    # motor" as readily as "3.2 Bearing Analysis".
    if HEADING_RE.match(line) or (line.isupper() and 2 <= len(line.split()) <= 8):
        return looks_like_title(line)
    return False


def _tables_to_text(tables) -> list[str]:
    out: list[str] = []
    for table in tables:
        rows = [" | ".join(cell or "" for cell in row) for row in table]
        out.append("\n".join(rows))
    return out


def _extract_tables_range(args: tuple[str, int, int]) -> dict[int, list[str]]:
    """Extract tables for pages [start, end) — module-level so it can be pickled.

    Runs in a worker process: pdfplumber is pure-Python and CPU-bound, so
    threads would serialize on the GIL.
    """
    pdf_path, start, end = args
    found: dict[int, list[str]] = {}
    try:
        import pdfplumber as _pp

        with _pp.open(pdf_path) as pdf:
            for idx in range(start, min(end, len(pdf.pages))):
                try:
                    tables = pdf.pages[idx].extract_tables() or []
                except Exception:
                    continue
                if tables:
                    found[idx + 1] = _tables_to_text(tables)
                # Release cached page objects; pdfplumber holds them otherwise.
                pdf.pages[idx].flush_cache()
    except Exception:
        return found
    return found


def _extract_tables_serial(pdf_path: Path, n_pages: int) -> dict[int, list[str]]:
    return _extract_tables_range((str(pdf_path), 0, n_pages))


def _extract_tables(pdf_path: Path, n_pages: int) -> dict[int, list[str]]:
    """Table text per 1-indexed page, extracted in parallel when worthwhile.

    pdfplumber dominates extraction on long documents (~60 ms/page regardless
    of whether the page has a table), so pages are split across worker
    processes. Falls back to serial on small documents or if the pool cannot
    start (restricted/sandboxed environments).
    """
    workers = max(1, min(PDF_TABLE_WORKERS, (os.cpu_count() or 2)))
    if workers == 1 or n_pages < PDF_TABLE_PARALLEL_MIN_PAGES:
        return _extract_tables_serial(pdf_path, n_pages)

    stride = math.ceil(n_pages / workers)
    ranges = [
        (str(pdf_path), start, min(start + stride, n_pages))
        for start in range(0, n_pages, stride)
    ]

    merged: dict[int, list[str]] = {}
    try:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for partial in pool.map(_extract_tables_range, ranges):
                merged.update(partial)
    except Exception as exc:  # noqa: BLE001 — never fail ingest over tables
        logger.warning("Parallel table extraction failed (%s); using serial", exc)
        return _extract_tables_serial(pdf_path, n_pages)
    return merged


def _extract_pages(pdf_path: Path) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    with fitz.open(pdf_path) as doc:
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            pages.append({"page_num": i, "text": text})

    try:
        for page_num, table_texts in _extract_tables(pdf_path, len(pages)).items():
            if 1 <= page_num <= len(pages):
                pages[page_num - 1]["tables"] = table_texts
    except Exception:
        pass

    return pages


def _build_nodes(pages: list[dict[str, Any]], doc_id: str) -> list[StructuredNode]:
    nodes: list[StructuredNode] = []
    current_chapter: StructuredNode | None = None
    current_section: StructuredNode | None = None
    node_counter = 0

    def new_node(node_type: str, title: str, page: int, parent: StructuredNode | None) -> StructuredNode:
        nonlocal node_counter
        node_counter += 1
        path_parts: list[str] = []
        if current_chapter:
            path_parts.append(current_chapter.title)
        if node_type == "section" and current_chapter:
            path_parts.append(title)
        elif node_type == "clause":
            if current_chapter:
                path_parts.append(current_chapter.title)
            if current_section:
                path_parts.append(current_section.title)
            path_parts.append(title)
        section_path = " > ".join(path_parts) if path_parts else title
        node = StructuredNode(
            node_id=f"{doc_id}_{node_type}_{node_counter:04d}",
            node_type=node_type,
            title=title,
            page_start=page,
            page_end=page,
            section_path=section_path,
            parent_id=parent.node_id if parent else None,
        )
        nodes.append(node)
        if parent:
            parent.children.append(node.node_id)
        return node

    running = _running_lines(pages)

    for page in pages:
        page_num = page["page_num"]
        lines = [ln.strip() for ln in page["text"].splitlines() if ln.strip()]
        buffer: list[str] = []

        def flush_clause() -> None:
            nonlocal current_section, current_chapter
            if not buffer:
                return
            body = " ".join(buffer).strip()
            buffer.clear()
            if len(body) < 20:
                return
            parent = current_section or current_chapter
            title = body[:80].rstrip(".") + ("..." if len(body) > 80 else "")
            clause = new_node("clause", title, page_num, parent)
            clause.text = body
            clause.page_end = page_num

        for line in lines:
            if _is_heading(line, running):
                flush_clause()
                if CHAPTER_RE.match(line) or (line.isupper() and "CHAPTER" in line.upper()):
                    current_chapter = new_node("chapter", line, page_num, None)
                    current_section = None
                elif SECTION_RE.match(line) or NUMBERED_HEADING_RE.match(line):
                    current_section = new_node("section", line, page_num, current_chapter)
                else:
                    if current_section is None and current_chapter:
                        current_section = new_node("section", line, page_num, current_chapter)
                    elif current_chapter is None:
                        current_chapter = new_node("chapter", line, page_num, None)
            else:
                buffer.append(line)

        flush_clause()

        for table_text in page.get("tables", []):
            parent = current_section or current_chapter
            table_node = new_node("table", "Table", page_num, parent)
            table_node.text = table_text
            table_node.page_end = page_num

    # Back-fill headings with a preview of their children. Indexing children by
    # parent first keeps this linear; scanning all nodes per textless node was
    # O(n^2) and degrades sharply on heading-rich documents.
    children_by_parent: dict[str, list[StructuredNode]] = defaultdict(list)
    for node in nodes:
        if node.parent_id:
            children_by_parent[node.parent_id].append(node)

    for node in nodes:
        if not node.text:
            child_texts = [c.text for c in children_by_parent[node.node_id] if c.text]
            if child_texts:
                node.text = " ".join(child_texts[:3])[:500]

    return nodes


def _split_text(text: str, max_chars: int = 900) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return [text] if text else []
    parts: list[str] = []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    current = ""
    for sentence in sentences:
        if len(current) + len(sentence) + 1 <= max_chars:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                parts.append(current)
            current = sentence
    if current:
        parts.append(current)
    return parts


def _nodes_to_chunks(
    nodes: list[StructuredNode],
    meta: dict[str, Any],
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    chunk_num = 0

    type_map = {
        "chapter": "chapter_summary",
        "section": "section_summary",
        "clause": "clause",
        "table": "table",
    }

    for node in nodes:
        chunk_type = type_map.get(node.node_type, "clause")
        texts = _split_text(node.text) if node.text else []
        if not texts and node.title:
            texts = [node.title]

        for text in texts:
            chunk_num += 1
            chunks.append(
                {
                    "chunk_id": f"chunk_{chunk_num:06d}",
                    "chunk_type": chunk_type,
                    "text": text,
                    "node_id": node.node_id,
                    "page_start": node.page_start,
                    "page_end": node.page_end,
                    "section_path": node.section_path,
                    "meta": dict(meta),
                }
            )

    return chunks


def _extract_image_chunks(
    pdf_path: Path,
    output_dir: Path,
    meta: dict[str, Any],
    start_num: int = 0,
) -> list[dict[str, Any]]:
    """Save embedded figures to assets/ and return image chunks for them."""
    from app.config import MIN_IMAGE_PX

    assets_dir = output_dir / "assets"
    chunks: list[dict[str, Any]] = []
    chunk_num = start_num

    try:
        import fitz
    except ImportError:
        return chunks

    try:
        assets_dir.mkdir(parents=True, exist_ok=True)
        with fitz.open(pdf_path) as doc:
            for page_idx, page in enumerate(doc, start=1):
                for img_idx, img in enumerate(page.get_images(full=True)):
                    xref = img[0]
                    try:
                        base = doc.extract_image(xref)
                    except Exception:
                        continue
                    if not base or not base.get("image"):
                        continue
                    w = base.get("width", 0)
                    h = base.get("height", 0)
                    if w < MIN_IMAGE_PX or h < MIN_IMAGE_PX:
                        continue
                    ext = base.get("ext", "png")
                    fname = f"page{page_idx:03d}_img{img_idx:02d}.{ext}"
                    out_path = assets_dir / fname
                    try:
                        out_path.write_bytes(base["image"])
                    except Exception:
                        continue
                    chunk_num += 1
                    chunk_meta = dict(meta)
                    chunk_meta["asset_path"] = f"assets/{fname}"
                    chunks.append(
                        {
                            "chunk_id": f"chunk_{chunk_num:06d}",
                            "chunk_type": "image",
                            "text": f"Figure on page {page_idx}",
                            "node_id": f"{meta.get('doc_id', 'doc')}_image_{chunk_num:04d}",
                            "page_start": page_idx,
                            "page_end": page_idx,
                            "section_path": "Figures",
                            "meta": chunk_meta,
                        }
                    )
    except Exception:
        return chunks
    return chunks


def run_extraction(
    pdf_path: Path,
    output_dir: Path,
    doc_id: str,
    title: str | None = None,
) -> dict[str, Any]:
    """Extract PDF → registry + structured_nodes + chunks.jsonl."""
    output_dir.mkdir(parents=True, exist_ok=True)

    display_title = title or doc_id.replace("_", " ").title()
    registry = {
        "doc_id": doc_id,
        "title": display_title,
        "department": "",
        "version": "",
        "effective_date": "",
        "confidentiality": "",
        "source_path": str(pdf_path),
    }

    pages = _extract_pages(pdf_path)
    nodes = _build_nodes(pages, doc_id)
    meta = {
        "doc_id": doc_id,
        "title": display_title,
        "department": "",
        "version": "",
        "effective_date": "",
        "confidentiality": "",
    }
    chunks = _nodes_to_chunks(nodes, meta)

    # Extract embedded figures (fast, PyMuPDF) so the vision-enrichment step can
    # caption them even on this lightweight digital path. Image chunks carry an
    # asset_path in meta, matching the multimodal pipeline's chunk schema.
    image_chunks = _extract_image_chunks(pdf_path, output_dir, meta, start_num=len(chunks))
    chunks.extend(image_chunks)

    registry_path = output_dir / "document_registry.json"
    nodes_path = output_dir / "structured_nodes.json"
    chunks_path = output_dir / "chunks.jsonl"

    registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    nodes_path.write_text(
        json.dumps(
            [
                {
                    "node_id": n.node_id,
                    "node_type": n.node_type,
                    "title": n.title,
                    "page_start": n.page_start,
                    "page_end": n.page_end,
                    "section_path": n.section_path,
                    "text": n.text,
                    "children": n.children,
                    "parent_id": n.parent_id,
                }
                for n in nodes
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    with chunks_path.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    return {
        "registry": registry,
        "chunk_count": len(chunks),
        "paths": {
            "registry": str(registry_path),
            "nodes": str(nodes_path),
            "chunks": str(chunks_path),
        },
    }
