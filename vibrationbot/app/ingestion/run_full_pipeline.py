"""
Single entry: extract → vision enrich → filter → sanitize → index.

PDF routing (applied before any extraction):

  digital  → document_pdf_pipeline  (PyMuPDF + pdfplumber, fast, no OCR)
  scanned  → document_multimodal_pipeline with OCR enabled (memory-safe windows)
  hybrid   → document_multimodal_pipeline, OCR only on image-only regions

DOCX always goes through document_multimodal_pipeline with a python-docx fallback.
"""

from __future__ import annotations

from pathlib import Path

from app.config import DIGITAL_PDF_USE_DOCLING
from app.ingestion import document_multimodal_pipeline
from app.ingestion import document_pdf_pipeline
from app.ingestion import filter_toc as filter_toc_mod
from app.ingestion import sanitize_section_path as sanitize_mod
from app.retrieval import faiss_index as index_mod
from app.ingestion import vision_enrichment
from app.ingestion.progress import step, success

PIPELINE_STEPS = 6


def run_full_pipeline(
    source_path: Path,
    output_dir: Path,
    doc_id: str,
    title: str | None = None,
    embedding_model: str = "BAAI/bge-small-en-v1.5",
    min_chunk_chars: int = 40,
    verbose: bool = True,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = source_path.suffix.lower()

    def log(n: int, msg: str) -> None:
        if verbose:
            step(n, PIPELINE_STEPS, msg, doc_id=doc_id)

    # --- Classify PDF before extraction so we pick the right pipeline ---
    pdf_kind: str = "digital"
    if suffix == ".pdf":
        from app.ingestion.docling_config import classify_pdf
        info = classify_pdf(source_path)
        pdf_kind = info["kind"]
        log(1, (
            f"PDF classified as '{pdf_kind}' "
            f"(text on {info['text_ratio']:.0%} of sampled pages, "
            f"{info['page_count']} pages, {info['size_mb']:.1f} MB)"
        ))

    log(1, f"Extracting content from {source_path.name} ...")

    if suffix == ".docx":
        # DOCX always through multimodal pipeline (handles tables + embedded images).
        extraction = document_multimodal_pipeline.run_extraction(
            source_path=source_path,
            output_dir=output_dir,
            doc_id=doc_id,
            title=title,
        )
    elif suffix == ".pdf":
        if pdf_kind == "digital" and not DIGITAL_PDF_USE_DOCLING:
            # Selectable text layer → fast PyMuPDF + pdfplumber extraction
            # (seconds, no heavy layout models, no OCR). Figures are still
            # extracted so vision enrichment can caption them.
            log(1, "Using fast PyMuPDF extractor (digital PDF)")
            extraction = document_pdf_pipeline.run_extraction(
                pdf_path=source_path,
                output_dir=output_dir,
                doc_id=doc_id,
                title=title,
            )
        elif pdf_kind == "digital":
            # Digital but DIGITAL_PDF_USE_DOCLING=true → Docling without OCR
            # for richer layout/table structure (slower).
            log(1, "Using Docling extractor (digital PDF, OCR off)")
            extraction = document_multimodal_pipeline.run_extraction(
                source_path=source_path,
                output_dir=output_dir,
                doc_id=doc_id,
                title=title,
                force_ocr=False,
            )
        else:
            # scanned or hybrid — OCR is required; use Docling (windowed, memory-safe).
            log(1, f"Using Docling extractor + OCR ({pdf_kind} PDF)")
            extraction = document_multimodal_pipeline.run_extraction(
                source_path=source_path,
                output_dir=output_dir,
                doc_id=doc_id,
                title=title,
                force_ocr=True,
            )
    else:
        raise ValueError(f"Unsupported file format: {suffix}")

    log(1, f"Extraction done — {extraction['chunk_count']} raw chunks")

    chunks_path = output_dir / "chunks.jsonl"
    log(2, "Vision enrichment (figures/charts) ...")
    enriched = vision_enrichment.enrich_chunks(chunks_path, output_dir)
    log(2, f"Vision enrichment done — {enriched} figure(s) captioned")

    clean_path = output_dir / "chunks_clean.jsonl"
    sanitized_path = output_dir / "chunks_sanitized.jsonl"
    index_dir = output_dir / "faiss_index"

    log(3, "Filtering TOC / noise ...")
    clean_count = filter_toc_mod.filter_chunks(
        chunks_path, clean_path, min_chars=min_chunk_chars
    )
    log(3, f"Filter done — {clean_count} chunks kept")

    log(4, "Sanitizing section paths ...")
    sanitized_count = sanitize_mod.sanitize_chunks(clean_path, sanitized_path)

    source_for_index = sanitized_path
    if sanitized_count == 0 and chunks_path.exists():
        sanitize_mod.sanitize_chunks(chunks_path, sanitized_path)
        source_for_index = sanitized_path
    log(4, f"Sanitize done — {sanitized_count or 'fallback'} chunks")

    log(5, f"Building FAISS index ({embedding_model}) ...")
    indexed_count = index_mod.build_faiss_index(
        source_for_index, index_dir, embedding_model
    )
    log(5, f"FAISS index built — {indexed_count} vectors")

    log(6, "Pipeline complete")
    if verbose:
        success(f"{doc_id}: ready ({indexed_count} chunks indexed)")

    return {
        "doc_id": doc_id,
        "pdf_kind": pdf_kind,
        "chunk_count": extraction["chunk_count"],
        "clean_count": clean_count,
        "sanitized_count": sanitized_count or indexed_count,
        "indexed_count": indexed_count,
        "enriched_figures": enriched,
        "index_dir": str(index_dir),
        "embedding_model": embedding_model,
    }
