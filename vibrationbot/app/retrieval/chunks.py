"""Single-chunk lookup by id.

Lives here rather than in ingestion: it reads through index_service and has no
pipeline dependency at all. Keeping it in ingest_service meant chat imported
app.ingestion - and therefore Docling and PyMuPDF - for one dict lookup.
"""

from __future__ import annotations

from app.config import DOCUMENTS_DIR
from app.retrieval.index_service import index_service


def get_chunk_by_id(doc_id: str, chunk_id: str) -> dict | None:
    if not (DOCUMENTS_DIR / doc_id).exists():
        return None
    return index_service.load_chunk_map(doc_id).get(chunk_id)
