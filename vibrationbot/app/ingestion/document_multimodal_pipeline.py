"""
Layout-aware PDF/DOCX extraction with tables, figures, and text chunking.
Falls back to document_pdf_pipeline for PDF when Docling is unavailable.
"""

from __future__ import annotations

import gc
import json
import logging
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DegenerateExtraction(RuntimeError):
    """Raised when Docling produced too little content to trust (e.g. mass OOM)."""

HEADING_RE = re.compile(r"^#{1,4}\s+(.+)$")
MIN_IMAGE_PX = 80
# Hard ceiling on section nesting. Without it section_path accumulates every
# heading in the document (the stack was appended to but never popped), so a
# long technical PDF produced multi-kilobyte paths duplicated into every node,
# every chunk, and every FAISS metadata entry.
MAX_SECTION_DEPTH = 6


def _push_section(section_stack: list[str], title: str, level: Any) -> None:
    """Push a heading, truncating deeper levels so the stack stays bounded.

    Docling's per-item ``level`` is the tree depth. When it is unusable we fall
    back to appending, but the hard cap still applies either way.
    """
    if isinstance(level, int) and 0 <= level < MAX_SECTION_DEPTH:
        del section_stack[level:]
    section_stack.append(title)
    # Drop from the front, not the back: when the cap is hit the *innermost*
    # headings are the relevant context, so the oldest ancestors are shed.
    # (Trimming the tail instead would freeze section_path on the document's
    # opening headings.)
    if len(section_stack) > MAX_SECTION_DEPTH:
        del section_stack[: len(section_stack) - MAX_SECTION_DEPTH]


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
    extra: dict[str, Any] = field(default_factory=dict)


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


def _table_to_markdown(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    cleaned = [[(cell or "").strip() for cell in row] for row in rows]
    if not any(any(c for c in row) for row in cleaned):
        return ""
    header = cleaned[0]
    body = cleaned[1:] if len(cleaned) > 1 else []
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in body:
        padded = row + [""] * (len(header) - len(row))
        lines.append("| " + " | ".join(padded[: len(header)]) + " |")
    return "\n".join(lines)


def _extract_pdf_images(pdf_path: Path, assets_dir: Path) -> list[dict[str, Any]]:
    figures: list[dict[str, Any]] = []
    try:
        import fitz
    except ImportError:
        return figures

    assets_dir.mkdir(parents=True, exist_ok=True)
    with fitz.open(pdf_path) as doc:
        for page_idx, page in enumerate(doc, start=1):
            for img_idx, img in enumerate(page.get_images(full=True)):
                xref = img[0]
                try:
                    base = doc.extract_image(xref)
                    if not base or not base.get("image"):
                        continue
                    w = base.get("width", 0)
                    h = base.get("height", 0)
                    if w < MIN_IMAGE_PX or h < MIN_IMAGE_PX:
                        continue
                    ext = base.get("ext", "png")
                    fname = f"page{page_idx:03d}_img{img_idx:02d}.{ext}"
                    out_path = assets_dir / fname
                    out_path.write_bytes(base["image"])
                    figures.append(
                        {
                            "asset_path": f"assets/{fname}",
                            "page": page_idx,
                            "width": w,
                            "height": h,
                            "caption": "",
                        }
                    )
                except Exception:
                    continue
    return figures


def _split_pdf_window(
    src: Any, start: int, end: int, out_pdf: Path, src_name: str = "pdf"
) -> bool:
    """Write pages [start, end] (1-indexed, inclusive) of an open PDF to out_pdf.

    Returns True on success. Splitting lets Docling parse only a few pages per
    conversion, which keeps memory bounded and avoids re-parsing the whole
    document for every window.

    Takes an already-open document rather than a path: the caller opens the
    source once for the whole run instead of reopening it per window (50 times
    for a 500-page PDF at the default batch size).
    """
    try:
        import fitz

        with fitz.open() as dst:
            dst.insert_pdf(src, from_page=start - 1, to_page=end - 1)
            dst.save(str(out_pdf))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to split %s pages %d-%d: %s", src_name, start, end, exc)
        return False


def _process_docling_document(
    doc: Any,
    doc_id: str,
    assets_dir: Path,
    nodes: list[StructuredNode],
    section_stack: list[str],
    pages_with_content: set[int],
    page_offset: int = 0,
) -> None:
    """Append StructuredNodes for one Docling document (one page window).

    ``page_offset`` is added to Docling's per-window page numbers so absolute
    page numbers are preserved when the source was split into sub-PDFs.
    """

    def new_node(
        node_type: str,
        title: str,
        page: int,
        text: str = "",
        extra: dict[str, Any] | None = None,
    ) -> StructuredNode:
        section_path = " > ".join(section_stack) if section_stack else title
        node = StructuredNode(
            node_id=f"{doc_id}_{node_type}_{len(nodes) + 1:04d}",
            node_type=node_type,
            title=title,
            page_start=page,
            page_end=page,
            section_path=section_path,
            text=text,
            extra=extra or {},
        )
        nodes.append(node)
        if text.strip():
            pages_with_content.add(page)
        return node

    try:
        from docling_core.types.doc import PictureItem, TableItem, TextItem

        for item, level in doc.iterate_items():
            page = 1
            if hasattr(item, "prov") and item.prov:
                page = getattr(item.prov[0], "page_no", 1) or 1
            page += page_offset

            if isinstance(item, TextItem):
                text = (item.text or "").strip()
                if not text:
                    continue
                if HEADING_RE.match(text) or (text.isupper() and len(text.split()) <= 10):
                    _push_section(section_stack, text[:120], level)
                    new_node("section", text[:120], page, text)
                else:
                    parent_title = section_stack[-1] if section_stack else "Document"
                    new_node("clause", parent_title[:80], page, text)

            elif isinstance(item, TableItem):
                md = ""
                try:
                    md = item.export_to_markdown(doc=doc)
                except Exception:
                    pass
                if not md:
                    continue
                new_node("table", "Table", page, md, extra={"table_markdown": md})

            elif isinstance(item, PictureItem):
                fname = f"figure_{len(nodes) + 1:04d}.png"
                out_path = assets_dir / fname
                assets_dir.mkdir(parents=True, exist_ok=True)
                try:
                    item.get_image(doc).save(out_path, "PNG")
                except Exception:
                    continue
                caption = getattr(item, "caption", "") or ""
                new_node(
                    "image",
                    "Figure",
                    page,
                    caption or f"Figure on page {page}",
                    extra={"asset_path": f"assets/{fname}", "caption": caption},
                )
    except ImportError:
        md = doc.export_to_markdown()
        _chunk_markdown(md, new_node, nodes)


def _extract_with_docling(
    source_path: Path,
    doc_id: str,
    assets_dir: Path,
    light: bool = False,
    force_ocr: bool | None = None,
) -> list[StructuredNode]:
    """Run Docling extraction with optional OCR override.

    ``force_ocr=True``  → OCR always on (scanned / hybrid PDFs).
    ``force_ocr=False`` → OCR always off (digital PDFs with a text layer).
    ``force_ocr=None``  → auto: disable OCR when a text layer is detected,
                           otherwise fall back to the ``DOCLING_DO_OCR`` env var.
    """
    from app.config import DOCLING_MIN_PAGE_COVERAGE, DOCLING_PAGE_BATCH
    from app.ingestion.docling_config import build_converter, page_count, pdf_stats

    is_pdf = source_path.suffix.lower() == ".pdf"

    enable_ocr: bool | None = force_ocr  # caller wins if set
    total_pages = 0
    if is_pdf:
        stats = pdf_stats(source_path)
        total_pages = stats["page_count"]
        if force_ocr is None:
            # Auto-detect: text layer present → skip OCR (saves memory & time).
            if stats["has_text"]:
                enable_ocr = False
                logger.info(
                    "PDF has text layer (%d pages, %.1f MB) — OCR auto-disabled",
                    stats["page_count"],
                    stats["size_mb"],
                )
            # else: leave enable_ocr=None so build_converter reads DOCLING_DO_OCR
        else:
            logger.info(
                "OCR %s (forced by caller) for %s",
                "enabled" if force_ocr else "disabled",
                source_path.name,
            )

    converter = build_converter(light=light, enable_ocr=enable_ocr)

    nodes: list[StructuredNode] = []
    section_stack: list[str] = []
    pages_with_content: set[int] = set()

    if not is_pdf:
        # DOCX / other: single conversion, no page windowing.
        result = converter.convert(str(source_path), raises_on_error=False)
        _process_docling_document(
            result.document, doc_id, assets_dir, nodes, section_stack, pages_with_content
        )
        del result
        gc.collect()
        return nodes

    if total_pages <= 0:
        total_pages = page_count(source_path)

    if total_pages <= 0:
        # Unknown length — fall back to a single conversion.
        result = converter.convert(str(source_path), raises_on_error=False)
        _process_docling_document(
            result.document, doc_id, assets_dir, nodes, section_stack, pages_with_content
        )
        del result
        gc.collect()
        return nodes

    batch = max(1, DOCLING_PAGE_BATCH)
    # Split the PDF into small sub-PDFs and convert each independently. Each
    # conversion parses only a handful of pages, so memory stays bounded (no
    # std::bad_alloc) and we avoid re-parsing the whole document per window.
    windows = [
        (start, min(start + batch - 1, total_pages))
        for start in range(1, total_pages + 1, batch)
    ]

    import fitz

    tmp_dir = Path(tempfile.mkdtemp(prefix=f"docling_{doc_id}_"))
    src_doc = fitz.open(source_path)
    try:
        for start, end in windows:
            sub_pdf = tmp_dir / f"window_{start:05d}_{end:05d}.pdf"
            if not _split_pdf_window(src_doc, start, end, sub_pdf, source_path.name):
                continue
            try:
                result = converter.convert(str(sub_pdf), raises_on_error=False)
                _process_docling_document(
                    result.document,
                    doc_id,
                    assets_dir,
                    nodes,
                    section_stack,
                    pages_with_content,
                    page_offset=start - 1,
                )
                del result
            except Exception as exc:  # noqa: BLE001 — keep going across windows
                logger.warning(
                    "Docling window pages %d-%d failed for %s: %s",
                    start,
                    end,
                    doc_id,
                    exc,
                )
            finally:
                try:
                    sub_pdf.unlink(missing_ok=True)
                except Exception:
                    pass
                gc.collect()
    finally:
        src_doc.close()
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # Degenerate-output guard: if Docling silently dropped most pages (OOM),
    # bail out so the caller falls back to the memory-safe PyMuPDF pipeline.
    if total_pages > 0:
        coverage = len(pages_with_content) / total_pages
        if coverage < DOCLING_MIN_PAGE_COVERAGE:
            raise DegenerateExtraction(
                f"Docling covered only {len(pages_with_content)}/{total_pages} "
                f"pages ({coverage:.0%}); falling back to text extraction"
            )

    has_figures = any(n.node_type in ("image", "diagram") for n in nodes)
    if not has_figures:
        for fig in _extract_pdf_images(source_path, assets_dir):
            page = fig["page"]
            section_path = " > ".join(section_stack) if section_stack else "Figure"
            nodes.append(
                StructuredNode(
                    node_id=f"{doc_id}_image_{len(nodes) + 1:04d}",
                    node_type="image",
                    title="Figure",
                    page_start=page,
                    page_end=page,
                    section_path=section_path,
                    text=fig.get("caption") or f"Figure on page {page}",
                    extra={
                        "asset_path": fig["asset_path"],
                        "width": fig.get("width"),
                        "height": fig.get("height"),
                    },
                )
            )

    return nodes


def _chunk_markdown(md: str, new_node, nodes: list[StructuredNode]) -> None:
    section_stack: list[str] = []
    page = 1
    buffer: list[str] = []

    def flush() -> None:
        if not buffer:
            return
        body = "\n".join(buffer).strip()
        buffer.clear()
        if len(body) < 20:
            return
        title = section_stack[-1] if section_stack else "Document"
        new_node("clause", title[:80], page, body)

    for line in md.splitlines():
        if line.startswith("#"):
            flush()
            title = line.lstrip("#").strip()
            # Markdown heading depth ("##" -> 2) bounds the stack, matching
            # _push_section's behaviour on the primary Docling path.
            depth = len(line) - len(line.lstrip("#"))
            _push_section(section_stack, title, max(0, depth - 1))
            new_node("section", title[:120], page, title)
        elif line.strip().startswith("|"):
            if "---" not in line:
                flush()
                buffer = [line]
                flush()
        else:
            buffer.append(line)
    flush()


def _extract_docx_basic(source_path: Path, doc_id: str) -> list[StructuredNode]:
    from docx import Document as DocxDocument

    doc = DocxDocument(str(source_path))
    nodes: list[StructuredNode] = []
    node_counter = 0
    section = "Document"

    def new_node(
        node_type: str, title: str, text: str, extra: dict | None = None
    ) -> None:
        nonlocal node_counter
        node_counter += 1
        nodes.append(
            StructuredNode(
                node_id=f"{doc_id}_{node_type}_{node_counter:04d}",
                node_type=node_type,
                title=title,
                page_start=1,
                page_end=1,
                section_path=section,
                text=text,
                extra=extra or {},
            )
        )

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = (para.style.name or "").lower()
        if "heading" in style:
            section = text
            new_node("section", text[:120], text)
        else:
            new_node("clause", section[:80], text)

    for table in doc.tables:
        rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
        md = _table_to_markdown(rows)
        if md:
            new_node("table", "Table", md, extra={"table_markdown": md})

    return nodes


def _nodes_to_chunks(nodes: list[StructuredNode], meta: dict[str, Any]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    chunk_num = 0
    type_map = {
        "chapter": "chapter_summary",
        "section": "section_summary",
        "clause": "clause",
        "table": "table",
        "image": "image",
        "diagram": "diagram",
    }

    for node in nodes:
        chunk_type = type_map.get(node.node_type, "clause")
        texts = _split_text(node.text) if node.text else []
        if not texts and node.title:
            texts = [node.title]

        for text in texts:
            chunk_num += 1
            chunk_meta = dict(meta)
            if node.extra.get("table_markdown"):
                chunk_meta["table_markdown"] = node.extra["table_markdown"]
            if node.extra.get("asset_path"):
                chunk_meta["asset_path"] = node.extra["asset_path"]
            chunks.append(
                {
                    "chunk_id": f"chunk_{chunk_num:06d}",
                    "chunk_type": chunk_type,
                    "text": text,
                    "node_id": node.node_id,
                    "page_start": node.page_start,
                    "page_end": node.page_end,
                    "section_path": node.section_path,
                    "meta": chunk_meta,
                }
            )
    return chunks


def run_extraction(
    source_path: Path,
    output_dir: Path,
    doc_id: str,
    title: str | None = None,
    force_ocr: bool | None = None,
) -> dict[str, Any]:
    """Extract PDF/DOCX → registry + structured_nodes + chunks.jsonl.

    Args:
        force_ocr: Override OCR behaviour.
            ``True``  → always run OCR (scanned PDFs).
            ``False`` → never run OCR (digital PDFs with text layer).
            ``None``  → let the pipeline decide from ``DOCLING_DO_OCR`` env var.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = output_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    display_title = title or doc_id.replace("_", " ").title()
    registry = {
        "doc_id": doc_id,
        "title": display_title,
        "department": "",
        "version": "",
        "effective_date": "",
        "confidentiality": "",
        "source_path": str(source_path),
        "source_format": source_path.suffix.lower().lstrip("."),
    }

    nodes: list[StructuredNode] = []
    suffix = source_path.suffix.lower()

    if suffix == ".pdf":
        from app.ingestion.docling_config import pdf_stats, should_use_light_mode

        stats = pdf_stats(source_path)
        use_light = should_use_light_mode(source_path)
        if use_light:
            logger.info(
                "Light extraction for %s (%.1f MB, %d pages)",
                source_path.name,
                stats["size_mb"],
                stats["page_count"],
            )

        try:
            nodes = _extract_with_docling(
                source_path,
                doc_id,
                assets_dir,
                light=use_light,
                force_ocr=force_ocr,
            )
            logger.info("Docling extraction succeeded for %s (%d nodes)", doc_id, len(nodes))
        except Exception as exc:
            logger.warning(
                "Docling failed for %s (%s), falling back to PDF pipeline",
                doc_id,
                exc,
            )
            from app.ingestion import document_pdf_pipeline

            return document_pdf_pipeline.run_extraction(
                pdf_path=source_path,
                output_dir=output_dir,
                doc_id=doc_id,
                title=title,
            )
    elif suffix == ".docx":
        try:
            nodes = _extract_with_docling(source_path, doc_id, assets_dir)
        except Exception as exc:
            logger.warning("Docling failed for DOCX %s, using python-docx: %s", doc_id, exc)
            nodes = _extract_docx_basic(source_path, doc_id)
    else:
        raise ValueError(f"Unsupported format: {suffix}")

    if not nodes:
        raise ValueError(f"No content extracted from {source_path}")

    meta = {
        "doc_id": doc_id,
        "title": display_title,
        "department": "",
        "version": "",
        "effective_date": "",
        "confidentiality": "",
    }
    chunks = _nodes_to_chunks(nodes, meta)

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
                    **({"extra": n.extra} if n.extra else {}),
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
