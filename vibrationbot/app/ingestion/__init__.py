"""Document ingestion: source file in, searchable FAISS index out.

    ingest_service.py   upload/registry/status bookkeeping and the cross-process
                        ingest lock; the entry point the API and CLIs call
    run_full_pipeline.py  the six-step orchestration below
    docling_config.py   PDF classification heuristics + Docling converter setup
    document_pdf_pipeline.py        fast PyMuPDF/pdfplumber path (digital PDFs)
    document_multimodal_pipeline.py Docling path with OCR (scanned/hybrid, DOCX)
    vision_enrichment.py  figures and tables captioned into searchable prose
    filter_toc.py / sanitize_section_path.py  chunk cleanup
    progress.py         console step/banner output for the CLIs

classify -> extract -> vision enrich -> filter TOC -> sanitize paths -> index.
Only the last step reaches outside this package, to
``app.retrieval.faiss_index.build_faiss_index``.
"""
