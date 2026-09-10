"""Basic acceptance tests (no OpenAI required for ingest/retrieval)."""

from pathlib import Path

import pytest

from app.config import DOCUMENTS_DIR
from app.schemas import DocumentStatus
from app.ingestion import ingest_service
from app.retrieval.index_service import index_service
from app.retrieval.retrieval_service import (
    _chunk_type_boost,
    _is_follow_up,
    _retrieval_query_for_turn,
    retrieve_across_documents,
)

SAMPLE_PDF = Path(__file__).resolve().parent.parent / "sample_document.pdf"
SAMPLE_DOCX = Path(__file__).resolve().parent.parent / "sample_document.docx"


@pytest.fixture(scope="module")
def indexed_doc():
    if not SAMPLE_PDF.exists():
        pytest.skip("sample_document.pdf missing; run scripts/create_sample_pdf.py")
    result = ingest_service.process_document_upload(
        SAMPLE_PDF.read_bytes(),
        "sample_document.pdf",
        title="HR Document Manual",
        doc_id="test_sample_document",
    )
    assert result["status"] == DocumentStatus.READY
    return result["doc_id"]


@pytest.fixture(scope="module")
def indexed_docx():
    if not SAMPLE_DOCX.exists():
        pytest.skip("sample_document.docx missing; run scripts/create_sample_docx.py")
    result = ingest_service.process_document_upload(
        SAMPLE_DOCX.read_bytes(),
        "sample_document.docx",
        title="HR DOCX Manual",
        doc_id="test_sample_docx",
    )
    assert result["status"] == DocumentStatus.READY
    return result["doc_id"]


def test_ingest_creates_artifacts(indexed_doc):
    doc_dir = DOCUMENTS_DIR / indexed_doc
    assert (doc_dir / "chunks_sanitized.jsonl").exists()
    assert (doc_dir / "faiss_index").exists()
    detail = ingest_service.get_document_detail(indexed_doc)
    assert detail is not None
    assert detail["chunk_count"] > 0
    assert detail["status"] == DocumentStatus.READY


def test_docx_ingest(indexed_docx):
    doc_dir = DOCUMENTS_DIR / indexed_docx
    assert (doc_dir / "chunks_sanitized.jsonl").exists()
    assert (doc_dir / "faiss_index").exists()
    detail = ingest_service.get_document_detail(indexed_docx)
    assert detail is not None
    assert detail["chunk_count"] > 0


def test_retrieval_returns_sources(indexed_doc):
    vs = index_service.load_index(indexed_doc)
    results = retrieve_across_documents(
        {indexed_doc: vs},
        "casual leave",
        top_k=6,
        allowed_docs=[indexed_doc],
    )
    assert len(results) >= 1
    assert results[0]["section_path"]
    assert results[0]["page_start"] >= 1


def test_chunk_type_boost():
    assert _chunk_type_boost("show me the table values", "table") > 0
    assert _chunk_type_boost("what does the chart show", "image") > 0
    assert _chunk_type_boost("general policy", "clause") == 0


def test_follow_up_query_rewrite():
    assert _is_follow_up("explain in detail")
    rewritten = _retrieval_query_for_turn(
        "tell me more", "What is the casual leave section about?"
    )
    assert "casual leave" in rewritten.lower()


def test_doc_ids_filter(indexed_doc):
    vs = index_service.load_index(indexed_doc)
    results = retrieve_across_documents(
        {indexed_doc: vs},
        "annual leave",
        top_k=6,
        allowed_docs=[indexed_doc],
    )
    for r in results:
        assert r["doc_id"] == indexed_doc


def test_table_search_filter(indexed_docx):
    vs = index_service.load_index(indexed_docx)
    results = retrieve_across_documents(
        {indexed_docx: vs},
        "leave entitlements table",
        top_k=4,
        allowed_docs=[indexed_docx],
        chunk_types=["table"],
    )
    if results:
        assert all(r.get("chunk_type") == "table" for r in results)
