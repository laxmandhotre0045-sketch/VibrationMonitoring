from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

from langchain_community.vectorstores import FAISS

from app.config import DOCUMENTS_DIR, EMBEDDING_MODEL
from app.retrieval.faiss_index import load_faiss_index

logger = logging.getLogger(__name__)

READY_CACHE_TTL_SECONDS = 5.0


class IndexService:
    """Singleton cache for FAISS indexes and chunk lookup maps, per document."""

    def __init__(self) -> None:
        self._cache: dict[str, FAISS] = {}
        self._chunk_cache: dict[str, dict[str, dict]] = {}
        self._lock = threading.Lock()
        self._ready_cache: list[str] | None = None
        self._ready_cached_at: float = 0.0

    def doc_dir(self, doc_id: str) -> Path:
        return DOCUMENTS_DIR / doc_id

    def index_path(self, doc_id: str) -> Path:
        return self.doc_dir(doc_id) / "faiss_index"

    def status_path(self, doc_id: str) -> Path:
        return self.doc_dir(doc_id) / "status.json"

    def is_ready(self, doc_id: str) -> bool:
        status_file = self.status_path(doc_id)
        if not status_file.exists():
            return False
        try:
            status = json.loads(status_file.read_text(encoding="utf-8"))
            return status.get("status") == "ready"
        except Exception:
            return False

    def load_index(self, doc_id: str) -> FAISS:
        with self._lock:
            if doc_id in self._cache:
                return self._cache[doc_id]

            index_dir = self.index_path(doc_id)
            if not index_dir.exists():
                raise FileNotFoundError(f"FAISS index not found for doc_id={doc_id}")

            vectorstore = load_faiss_index(index_dir, EMBEDDING_MODEL)
            self._cache[doc_id] = vectorstore
            logger.info("Loaded FAISS index for %s", doc_id)
            return vectorstore

    def chunks_path(self, doc_id: str) -> Path:
        """Prefer the sanitized chunk file, matching what was indexed."""
        sanitized = self.doc_dir(doc_id) / "chunks_sanitized.jsonl"
        return sanitized if sanitized.exists() else self.doc_dir(doc_id) / "chunks.jsonl"

    def load_chunk_map(self, doc_id: str) -> dict[str, dict]:
        """Return {chunk_id: chunk} for a document, parsed once and cached.

        Without this, a single chunk lookup re-parsed the entire chunk file
        (~1700 json.loads for these documents), and an answer citing six
        figures did that six times.
        """
        with self._lock:
            cached = self._chunk_cache.get(doc_id)
            if cached is not None:
                return cached

            chunk_map: dict[str, dict] = {}
            path = self.chunks_path(doc_id)
            if path.exists():
                with path.open(encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        chunk = json.loads(line)
                        chunk_id = chunk.get("chunk_id", "")
                        if chunk_id:
                            chunk_map[chunk_id] = chunk
                logger.info("Loaded %d chunks for %s", len(chunk_map), doc_id)

            self._chunk_cache[doc_id] = chunk_map
            return chunk_map

    def invalidate(self, doc_id: str) -> None:
        with self._lock:
            self._cache.pop(doc_id, None)
            self._chunk_cache.pop(doc_id, None)

    def preload_ready_documents(self) -> list[str]:
        loaded: list[str] = []
        if not DOCUMENTS_DIR.exists():
            return loaded
        for doc_dir in DOCUMENTS_DIR.iterdir():
            if doc_dir.is_dir() and self.is_ready(doc_dir.name):
                try:
                    self.load_index(doc_dir.name)
                    loaded.append(doc_dir.name)
                except Exception as exc:
                    logger.warning("Failed to preload %s: %s", doc_dir.name, exc)
        return loaded

    def list_ready_doc_ids(self) -> list[str]:
        """Ready doc ids, cached briefly.

        Called on every chat request; uncached it walks DOCUMENTS_DIR and
        parses one status.json per document. The TTL is short enough that a
        newly-ready document appears without an explicit refresh, and ingest
        calls invalidate_ready() to make it immediate.
        """
        now = time.monotonic()
        with self._lock:
            if (
                self._ready_cache is not None
                and now - self._ready_cached_at < READY_CACHE_TTL_SECONDS
            ):
                return list(self._ready_cache)

        if not DOCUMENTS_DIR.exists():
            ready: list[str] = []
        else:
            ready = [
                d.name
                for d in DOCUMENTS_DIR.iterdir()
                if d.is_dir() and self.is_ready(d.name)
            ]

        with self._lock:
            self._ready_cache = ready
            self._ready_cached_at = time.monotonic()
        return list(ready)

    def invalidate_ready(self) -> None:
        """Force the next list_ready_doc_ids() to re-scan disk."""
        with self._lock:
            self._ready_cache = None
            self._ready_cached_at = 0.0


index_service = IndexService()
