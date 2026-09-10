from __future__ import annotations

import json
import logging
import os
import re
import time
from contextlib import contextmanager
from pathlib import Path

from app.config import (
    DATA_DIR,
    DOCUMENTS_DIR,
    EMBEDDING_MODEL,
    MIN_CHUNK_CHARS,
    SUPPORTED_EXTENSIONS,
)
from app.schemas import DocumentStatus
from app.ingestion.run_full_pipeline import run_full_pipeline
from app.retrieval.index_service import index_service

# Re-exported: the implementation lives in retrieval, which is where it
# belongs, but ingest_service.get_chunk_by_id remains the public name.
from app.retrieval.chunks import get_chunk_by_id  # noqa: F401

logger = logging.getLogger(__name__)


class IngestBusyError(RuntimeError):
    """Raised when another ingest is already running in this project."""


_LOCK_PATH = DATA_DIR / ".ingest.lock"
# A crashed/hard-killed ingest can't clean up; a lock older than this whose
# owner process is gone is considered abandoned and reclaimed.
_LOCK_STALE_SECONDS = 6 * 3600


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            import ctypes

            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        os.kill(pid, 0)
        return True
    except Exception:
        return False


@contextmanager
def _ingest_lock():
    """Serialize ingests across processes.

    Ingest is bounded by the OpenAI tokens-per-minute limit, and each process
    paces to a fraction of it. Two ingests at once would each pace to that
    fraction and their sum would exceed the account limit — the exact cause of
    the 429 storms. This lock guarantees a single active ingest; a second one
    fails fast with a clear message rather than silently thrashing.

    A stale lock (owner process gone, or older than the stale window) is
    reclaimed automatically so a crash never wedges ingest permanently.
    """
    _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    acquired = False
    try:
        while True:
            try:
                fd = os.open(str(_LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, f"{os.getpid()} {time.time()}".encode())
                os.close(fd)
                acquired = True
                break
            except FileExistsError:
                pid, ts = -1, 0.0
                try:
                    parts = _LOCK_PATH.read_text().split()
                    pid, ts = int(parts[0]), float(parts[1])
                except Exception:
                    pass
                stale = (not _pid_alive(pid)) or (time.time() - ts > _LOCK_STALE_SECONDS)
                if stale:
                    try:
                        _LOCK_PATH.unlink()
                    except FileNotFoundError:
                        pass
                    continue  # retry acquisition
                raise IngestBusyError(
                    f"Another ingest is already running (PID {pid}). Only one "
                    f"ingest runs at a time because they share the OpenAI "
                    f"rate limit. Wait for it to finish, then retry. "
                    f"(If you're sure none is running, delete {_LOCK_PATH}.)"
                )
        yield
    finally:
        if acquired:
            try:
                _LOCK_PATH.unlink()
            except FileNotFoundError:
                pass


def _slugify_doc_id(name: str) -> str:
    base = Path(name).stem
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", base.lower()).strip("_")
    return slug or "document"


def _unique_doc_id(base: str) -> str:
    candidate = base
    counter = 1
    while (DOCUMENTS_DIR / candidate).exists():
        candidate = f"{base}_{counter}"
        counter += 1
    return candidate


def _source_filename(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext == ".docx":
        return "source.docx"
    return "source.pdf"


def _write_status(
    doc_dir: Path,
    status: DocumentStatus,
    error: str = "",
    extra: dict | None = None,
) -> None:
    payload: dict = {"status": status.value, "error": error}
    if extra:
        payload.update(extra)
    (doc_dir / "status.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    # A document just changed readiness — drop the cached listing so the next
    # chat request sees it without waiting out the TTL.
    index_service.invalidate_ready()


def _patch_registry(doc_dir: Path, extra: dict) -> None:
    """Merge extra fields into the existing document_registry.json (if present)."""
    if not extra:
        return
    reg_path = doc_dir / "document_registry.json"
    if not reg_path.exists():
        return
    try:
        data = json.loads(reg_path.read_text(encoding="utf-8"))
        data.update(extra)
        reg_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not patch registry for %s: %s", doc_dir.name, exc)


def _count_chunks(doc_dir: Path) -> int:
    sanitized = doc_dir / "chunks_sanitized.jsonl"
    chunks_file = sanitized if sanitized.exists() else doc_dir / "chunks.jsonl"
    if not chunks_file.exists():
        return 0
    return sum(1 for line in chunks_file.open(encoding="utf-8") if line.strip())


def process_document_upload(
    file_bytes: bytes,
    filename: str,
    title: str | None = None,
    doc_id: str | None = None,
) -> dict:
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported format: {ext}. Supported: {', '.join(SUPPORTED_EXTENSIONS)}")

    # The lock wraps everything and sits OUTSIDE the pipeline try/except, so a
    # concurrent ingest raises IngestBusyError and propagates cleanly (no
    # half-created document dir, not misreported as a pipeline failure).
    with _ingest_lock():
        base_id = doc_id or _slugify_doc_id(filename)
        final_doc_id = _unique_doc_id(base_id) if not doc_id else base_id

        doc_dir = DOCUMENTS_DIR / final_doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)

        source_name = _source_filename(filename)
        source_path = doc_dir / source_name
        source_path.write_bytes(file_bytes)
        _write_status(doc_dir, DocumentStatus.PROCESSING)
        logger.info("Ingest started: doc_id=%s file=%s", final_doc_id, filename)

        try:
            index_service.invalidate(final_doc_id)
            result = run_full_pipeline(
                source_path=source_path,
                output_dir=doc_dir,
                doc_id=final_doc_id,
                title=title or Path(filename).stem.replace("_", " ").title(),
                embedding_model=EMBEDDING_MODEL,
                min_chunk_chars=MIN_CHUNK_CHARS,
                verbose=True,
            )
            pdf_kind = result.get("pdf_kind", "")
            _write_status(
                doc_dir,
                DocumentStatus.READY,
                extra={
                    "embedding_model": result.get("embedding_model", EMBEDDING_MODEL),
                    "chunk_count": result.get("indexed_count", 0),
                    "enriched_figures": result.get("enriched_figures", 0),
                    **({"pdf_kind": pdf_kind} if pdf_kind else {}),
                },
            )
            # Persist pdf_kind into the registry so downstream tools can see it.
            _patch_registry(doc_dir, {"pdf_kind": pdf_kind} if pdf_kind else {})
            index_service.load_index(final_doc_id)
            logger.info(
                "Ingest complete: doc_id=%s chunks=%s pdf_kind=%s",
                final_doc_id,
                result.get("indexed_count", 0),
                pdf_kind or "n/a",
            )
            return {
                "doc_id": final_doc_id,
                "status": DocumentStatus.READY,
                "chunk_count": result.get("indexed_count", _count_chunks(doc_dir)),
                **({"pdf_kind": pdf_kind} if pdf_kind else {}),
            }
        except Exception as exc:
            logger.exception("Pipeline failed for %s", final_doc_id)
            _write_status(doc_dir, DocumentStatus.FAILED, str(exc))
            return {
                "doc_id": final_doc_id,
                "status": DocumentStatus.FAILED,
                "error": str(exc),
            }


def get_document_status(doc_id: str) -> DocumentStatus:
    status_file = DOCUMENTS_DIR / doc_id / "status.json"
    if not status_file.exists():
        return DocumentStatus.FAILED
    data = json.loads(status_file.read_text(encoding="utf-8"))
    return DocumentStatus(data.get("status", "failed"))


def list_documents() -> list[dict]:
    if not DOCUMENTS_DIR.exists():
        return []

    docs: list[dict] = []
    for doc_dir in sorted(DOCUMENTS_DIR.iterdir()):
        if not doc_dir.is_dir():
            continue
        doc_id = doc_dir.name
        registry_path = doc_dir / "document_registry.json"
        title = doc_id
        if registry_path.exists():
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            title = registry.get("title", doc_id)

        status = get_document_status(doc_id)
        index_ready = (doc_dir / "faiss_index").exists() and status == DocumentStatus.READY
        docs.append(
            {
                "doc_id": doc_id,
                "title": title,
                "status": status,
                "chunk_count": _count_chunks(doc_dir),
                "index_status": "ready" if index_ready else "missing",
            }
        )
    return docs


def get_document_detail(doc_id: str) -> dict | None:
    doc_dir = DOCUMENTS_DIR / doc_id
    if not doc_dir.exists():
        return None

    registry_path = doc_dir / "document_registry.json"
    if not registry_path.exists():
        return None

    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    status = get_document_status(doc_id)
    index_ready = (doc_dir / "faiss_index").exists() and status == DocumentStatus.READY

    return {
        "doc_id": doc_id,
        "title": registry.get("title", doc_id),
        "status": status,
        "chunk_count": _count_chunks(doc_dir),
        "index_status": "ready" if index_ready else "missing",
        "registry": registry,
        "index_ready": index_ready,
    }


def run_pipeline_job(doc_id: str, source_path: Path, title: str) -> None:
    doc_dir = DOCUMENTS_DIR / doc_id
    logger.info("Background ingest started: doc_id=%s source=%s", doc_id, source_path.name)
    try:
        with _ingest_lock():
            index_service.invalidate(doc_id)
            result = run_full_pipeline(
                source_path=source_path,
                output_dir=doc_dir,
                doc_id=doc_id,
                title=title,
                embedding_model=EMBEDDING_MODEL,
                min_chunk_chars=MIN_CHUNK_CHARS,
                verbose=True,
            )
        pdf_kind = result.get("pdf_kind", "")
        _write_status(
            doc_dir,
            DocumentStatus.READY,
            extra={
                "embedding_model": result.get("embedding_model", EMBEDDING_MODEL),
                "chunk_count": result.get("indexed_count", 0),
                "enriched_figures": result.get("enriched_figures", 0),
                **({"pdf_kind": pdf_kind} if pdf_kind else {}),
            },
        )
        _patch_registry(doc_dir, {"pdf_kind": pdf_kind} if pdf_kind else {})
        index_service.load_index(doc_id)
        logger.info("Background ingest complete: doc_id=%s pdf_kind=%s", doc_id, pdf_kind or "n/a")
    except Exception as exc:
        logger.exception("Background pipeline failed for %s", doc_id)
        _write_status(doc_dir, DocumentStatus.FAILED, str(exc))


def get_chunks_page(doc_id: str, offset: int = 0, limit: int = 50) -> dict | None:
    doc_dir = DOCUMENTS_DIR / doc_id
    if not doc_dir.exists():
        return None

    chunks_file = doc_dir / "chunks_sanitized.jsonl"
    if not chunks_file.exists():
        chunks_file = doc_dir / "chunks.jsonl"
    if not chunks_file.exists():
        return {"doc_id": doc_id, "total": 0, "offset": offset, "limit": limit, "chunks": []}

    all_chunks = [
        json.loads(line)
        for line in chunks_file.open(encoding="utf-8")
        if line.strip()
    ]
    page = all_chunks[offset : offset + limit]
    return {
        "doc_id": doc_id,
        "total": len(all_chunks),
        "offset": offset,
        "limit": limit,
        "chunks": page,
    }


