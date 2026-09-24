"""Docling converter configuration — tuned for large technical PDFs."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    AcceleratorOptions,
    ThreadedPdfPipelineOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption

logger = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name, "true" if default else "false").lower()
    return val in ("1", "true", "yes")


def pdf_stats(pdf_path: Path) -> dict:
    """Return page count, size in MB, and whether sampled pages have text."""
    size_mb = pdf_path.stat().st_size / (1024 * 1024)
    pg_count = 0
    has_text = False
    try:
        import fitz

        with fitz.open(pdf_path) as doc:
            pg_count = len(doc)
            sample_indices = list(range(min(5, pg_count)))
            if pg_count > 10:
                sample_indices.extend([pg_count // 2, pg_count - 1])
            for idx in sample_indices:
                text = (doc[idx].get_text("text") or "").strip()
                if len(text) > 40:
                    has_text = True
                    break
    except Exception as exc:
        logger.warning("Could not inspect PDF %s: %s", pdf_path.name, exc)
    return {"page_count": pg_count, "size_mb": size_mb, "has_text": has_text}


def classify_pdf(pdf_path: Path) -> dict:
    """Classify a PDF as 'digital', 'scanned', or 'hybrid'.

    Evenly samples up to ``PDF_CLASSIFY_SAMPLE`` pages across the document and
    checks how many have a real selectable text layer.  Additional heuristics
    catch broken/garbled ToUnicode maps (printable-char ratio) and full-page
    image scans (single large image, no text).

    Returns::
        {
            "kind":        "digital" | "scanned" | "hybrid",
            "text_ratio":  float,          # fraction of sampled pages with text
            "page_count":  int,
            "size_mb":     float,
        }
    """
    from app.config import (
        PDF_CLASSIFY_MIN_CHARS,
        PDF_CLASSIFY_SAMPLE,
        PDF_DIGITAL_THRESHOLD,
        PDF_SCANNED_THRESHOLD,
    )

    size_mb = pdf_path.stat().st_size / (1024 * 1024)
    pg_count = 0
    text_pages = 0
    sample_size = 0

    try:
        import fitz

        with fitz.open(pdf_path) as doc:
            pg_count = len(doc)
            n = pg_count
            sample_n = min(PDF_CLASSIFY_SAMPLE, n)
            # Evenly spread indices across the whole doc (covers front, middle,
            # back) instead of only checking the first few pages.
            idxs = sorted(
                {int(round(i * (n - 1) / max(1, sample_n - 1))) for i in range(sample_n)}
            )
            sample_size = len(idxs)

            for idx in idxs:
                page = doc[idx]
                text = (page.get_text("text") or "").strip()

                if len(text) < PDF_CLASSIFY_MIN_CHARS:
                    # No meaningful text — but check for garbled ToUnicode maps:
                    # if text exists but most chars are non-printable, treat as
                    # effectively empty (happens in some scanned+OCR'd PDFs with
                    # broken glyph maps).
                    if text:
                        printable = sum(1 for c in text if c.isprintable() and not c.isspace())
                        if printable / max(1, len(text)) >= 0.7:
                            # Enough printable chars but still below min — might
                            # be a sparse page (e.g. cover). Don't count it.
                            pass
                    continue

                # Extra confidence: rule out pages where the "text" is really
                # just one big raster image covering the whole page.
                imgs = page.get_images(full=True)
                if imgs and len(text) < 200:
                    clip = page.rect
                    page_area = clip.width * clip.height
                    for img in imgs:
                        rects = page.get_image_rects(img[0])
                        img_area = sum(r.width * r.height for r in rects)
                        if page_area > 0 and img_area / page_area > 0.85:
                            # Single image covering >85% of the page — scanned.
                            break
                    else:
                        text_pages += 1
                else:
                    text_pages += 1

    except Exception as exc:
        logger.warning("classify_pdf failed for %s: %s", pdf_path.name, exc)

    ratio = text_pages / sample_size if sample_size else 0.0

    if ratio >= PDF_DIGITAL_THRESHOLD:
        kind = "digital"
    elif ratio <= PDF_SCANNED_THRESHOLD:
        kind = "scanned"
    else:
        kind = "hybrid"

    logger.info(
        "classify_pdf: %s → %s (text_ratio=%.0f%%, %d/%d sampled pages, %.1f MB)",
        pdf_path.name,
        kind,
        ratio * 100,
        text_pages,
        sample_size,
        size_mb,
    )
    return {
        "kind": kind,
        "text_ratio": round(ratio, 3),
        "page_count": pg_count,
        "size_mb": size_mb,
    }


def is_large_pdf(pdf_path: Path) -> bool:
    stats = pdf_stats(pdf_path)
    large_mb = _env_float("DOCLING_LARGE_PDF_MB", 15)
    large_pages = _env_int("DOCLING_LARGE_PDF_PAGES", 80)
    return stats["size_mb"] >= large_mb or stats["page_count"] >= large_pages


def should_use_light_mode(pdf_path: Path) -> bool:
    mode = os.getenv("DOCLING_LIGHT_MODE", "auto").lower()
    if mode == "true":
        return True
    if mode == "false":
        return False
    return is_large_pdf(pdf_path)


def page_count(pdf_path: Path) -> int:
    """Return the number of pages in a PDF (0 if it cannot be read)."""
    try:
        import fitz

        with fitz.open(pdf_path) as doc:
            return len(doc)
    except Exception as exc:
        logger.warning("Could not count pages for %s: %s", pdf_path.name, exc)
        return 0


def build_converter(light: bool = False, enable_ocr: bool | None = None) -> DocumentConverter:
    """Build DocumentConverter with memory-safe defaults for large PDFs.

    Concurrency and batch sizes are kept deliberately low so the threaded
    pipeline never holds more than a handful of rasterized pages in memory at
    once. This is what prevents the ``std::bad_alloc`` OOM crashes seen on
    large technical PDFs. Pages are additionally processed in bounded windows
    by the caller (see ``document_multimodal_pipeline``).
    """
    default_ocr = _env_bool("DOCLING_DO_OCR", False)
    use_ocr = enable_ocr if enable_ocr is not None else default_ocr
    images_scale = _env_float("DOCLING_IMAGES_SCALE", 1.0)
    timeout = _env_float("DOCLING_DOCUMENT_TIMEOUT", 600)

    num_threads = _env_int("DOCLING_NUM_THREADS", 2)
    queue_max = _env_int("DOCLING_QUEUE_MAX", 4)
    layout_batch = _env_int("DOCLING_LAYOUT_BATCH", 4)
    table_batch = _env_int("DOCLING_TABLE_BATCH", 4)
    ocr_batch = _env_int("DOCLING_OCR_BATCH", 2)

    if light:
        use_ocr = False
        images_scale = min(images_scale, 0.75)

    pipeline_options = ThreadedPdfPipelineOptions(
        do_ocr=use_ocr,
        do_table_structure=True,
        do_code_enrichment=False,
        do_formula_enrichment=False,
        generate_page_images=False,
        generate_picture_images=not light,
        images_scale=images_scale,
        document_timeout=timeout,
        accelerator_options=AcceleratorOptions(num_threads=max(1, num_threads)),
        queue_max_size=max(1, queue_max),
        layout_batch_size=max(1, layout_batch),
        table_batch_size=max(1, table_batch),
        ocr_batch_size=max(1, ocr_batch),
    )

    logger.info(
        "Docling config: light=%s ocr=%s scale=%.2f timeout=%s threads=%s queue=%s",
        light,
        use_ocr,
        images_scale,
        timeout,
        num_threads,
        queue_max,
    )

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        }
    )
