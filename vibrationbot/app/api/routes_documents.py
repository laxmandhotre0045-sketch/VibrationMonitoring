from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from app.config import DOCUMENTS_DIR, SUPPORTED_EXTENSIONS
from app.schemas import (
    ChunksPage,
    DocumentDetail,
    DocumentStatus,
    DocumentSummary,
    DocumentUploadResponse,
)
from app.ingestion import ingest_service

router = APIRouter(prefix="/documents", tags=["documents"])


# doc_id is used as a filesystem path segment. _slugify_doc_id only ever emits
# [a-z0-9_], but doc_id can also be supplied directly by the caller on upload,
# so it is validated everywhere it reaches the filesystem. Dots are excluded so
# ".." can never be formed.
DOC_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _safe_doc_id(doc_id: str) -> str:
    if not doc_id or not DOC_ID_RE.match(doc_id):
        raise HTTPException(status_code=400, detail="Invalid document id")
    return doc_id


def _safe_asset_path(doc_id: str, filename: str) -> Path:
    """Resolve an asset path, refusing anything outside the document's assets dir."""
    assets_dir = (DOCUMENTS_DIR / _safe_doc_id(doc_id) / "assets").resolve()
    target = (assets_dir / filename).resolve()
    # Containment check, not string matching: catches traversal via "..",
    # absolute paths, and symlinks that point outside the directory.
    if not target.is_relative_to(assets_dir):
        raise HTTPException(status_code=404, detail="Asset not found")
    return target


def _validate_extension(filename: str) -> None:
    if not filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Only {', '.join(sorted(SUPPORTED_EXTENSIONS))} files are supported",
        )


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str | None = None,
    doc_id: str | None = None,
    async_process: bool = Query(False, description="Process in background"),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    _validate_extension(file.filename)
    if doc_id is not None:
        _safe_doc_id(doc_id)

    content = await file.read()
    source_name = ingest_service._source_filename(file.filename)

    if async_process:
        doc_slug = doc_id or ingest_service._slugify_doc_id(file.filename)
        final_id = ingest_service._unique_doc_id(doc_slug) if not doc_id else doc_id
        doc_dir = DOCUMENTS_DIR / final_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        (doc_dir / source_name).write_bytes(content)
        ingest_service._write_status(doc_dir, DocumentStatus.PROCESSING)
        background_tasks.add_task(
            ingest_service.run_pipeline_job,
            final_id,
            doc_dir / source_name,
            title or file.filename,
        )
        return DocumentUploadResponse(doc_id=final_id, status=DocumentStatus.PROCESSING)

    # run_in_threadpool is required: the pipeline is synchronous and runs for
    # minutes (Docling/OCR + embedding every chunk). Calling it directly from
    # this coroutine blocks the event loop, freezing every other request —
    # health checks included — until ingest finishes.
    result = await run_in_threadpool(
        ingest_service.process_document_upload, content, file.filename, title, doc_id
    )
    if result["status"] == DocumentStatus.FAILED:
        raise HTTPException(status_code=500, detail=result.get("error", "Processing failed"))
    return DocumentUploadResponse(doc_id=result["doc_id"], status=result["status"])


@router.get("", response_model=list[DocumentSummary])
def list_documents():
    return ingest_service.list_documents()


@router.get("/{doc_id}", response_model=DocumentDetail)
def get_document(doc_id: str):
    detail = ingest_service.get_document_detail(_safe_doc_id(doc_id))
    if not detail:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    return detail


@router.get("/{doc_id}/chunks", response_model=ChunksPage)
def get_document_chunks(
    doc_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    page = ingest_service.get_chunks_page(_safe_doc_id(doc_id), offset, limit)
    if page is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    return page


@router.get("/{doc_id}/assets/{filename}")
def get_document_asset(doc_id: str, filename: str):
    asset_path = _safe_asset_path(doc_id, filename)
    if not asset_path.exists() or not asset_path.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(asset_path)
