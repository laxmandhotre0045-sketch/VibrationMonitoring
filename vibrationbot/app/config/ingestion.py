"""Document extraction: chunking, Docling behaviour, and PDF classification."""

import os as _os

MIN_CHUNK_CHARS = int(_os.getenv("MIN_CHUNK_CHARS", "40"))

# Docling settings (DOCLING_DO_OCR, DOCLING_LIGHT_MODE, DOCLING_NUM_THREADS,
# the batch sizes, the large-PDF thresholds and the document timeout) are NOT
# defined here: app/ingestion/docling_config.py reads those env vars directly
# through its own _env_bool/_env_int/_env_float helpers, at converter-build
# time. They used to be declared in both places with defaults that could drift
# apart, and only the docling_config copy was ever consulted.
#
# The two below are the exception - they are imported from here by
# document_multimodal_pipeline.
DOCLING_PAGE_BATCH = int(_os.getenv("DOCLING_PAGE_BATCH", "10"))
# Fraction of pages that must yield content before we trust Docling output.
# Below this, we fall back to the memory-safe PyMuPDF text pipeline.
DOCLING_MIN_PAGE_COVERAGE = float(_os.getenv("DOCLING_MIN_PAGE_COVERAGE", "0.5"))

# PDF type classification — sampled pages with >= MIN_CHARS characters count
# as "digital". text_ratio >= DIGITAL_THRESHOLD → digital (no OCR needed),
# text_ratio <= SCANNED_THRESHOLD → scanned (OCR required),
# anything in-between → hybrid (Docling OCR only on image pages).
# pdfplumber table extraction costs ~60ms/page whether or not the page has a
# table, and no cheap pre-filter exists (PyMuPDF find_tables costs as much as
# the extraction itself). Pages are split across processes instead — it is
# pure-Python and CPU-bound, so threads would serialize on the GIL.
PDF_TABLE_WORKERS = int(_os.getenv("PDF_TABLE_WORKERS", "8"))
# Below this page count, process startup outweighs the saving.
PDF_TABLE_PARALLEL_MIN_PAGES = int(_os.getenv("PDF_TABLE_PARALLEL_MIN_PAGES", "40"))

PDF_CLASSIFY_SAMPLE = int(_os.getenv("PDF_CLASSIFY_SAMPLE", "12"))
PDF_CLASSIFY_MIN_CHARS = int(_os.getenv("PDF_CLASSIFY_MIN_CHARS", "100"))
PDF_DIGITAL_THRESHOLD = float(_os.getenv("PDF_DIGITAL_THRESHOLD", "0.8"))
PDF_SCANNED_THRESHOLD = float(_os.getenv("PDF_SCANNED_THRESHOLD", "0.15"))
# Digital PDFs use the fast PyMuPDF/pdfplumber extractor by default (seconds,
# no heavy layout models). Set true to route digital PDFs through Docling
# instead for richer layout/table structure (much slower on large docs).
DIGITAL_PDF_USE_DOCLING = _os.getenv("DIGITAL_PDF_USE_DOCLING", "false").lower() in (
    "1",
    "true",
    "yes",
)
