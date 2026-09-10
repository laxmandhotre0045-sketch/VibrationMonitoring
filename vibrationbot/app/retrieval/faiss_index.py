"""
Build FAISS vector index from chunks_sanitized.jsonl.
"""

from __future__ import annotations

import json
from pathlib import Path

from langchain_community.vectorstores import FAISS

from app.retrieval.embeddings import get_embeddings
from langchain_core.documents import Document


def _load_chunks(chunks_path: Path) -> list[dict]:
    chunks: list[dict] = []
    with chunks_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    return chunks


def _chunk_to_document(chunk: dict) -> Document:
    meta = dict(chunk.get("meta") or {})
    page_content = chunk.get("text") or ""
    metadata = {
        "chunk_id": chunk.get("chunk_id", ""),
        "chunk_type": chunk.get("chunk_type", "clause"),
        "page_start": chunk.get("page_start", 0),
        "page_end": chunk.get("page_end", 0),
        "section_path": chunk.get("section_path", ""),
        "node_id": chunk.get("node_id", ""),
        "doc_id": meta.get("doc_id", ""),
        "asset_path": meta.get("asset_path", ""),
        **{k: v for k, v in meta.items() if k not in ("doc_id", "asset_path")},
    }
    return Document(page_content=page_content, metadata=metadata)


def build_faiss_index(
    chunks_path: Path,
    index_dir: Path,
    embedding_model: str,
) -> int:
    chunks = _load_chunks(chunks_path)
    if not chunks:
        raise ValueError(f"No chunks found in {chunks_path}")

    embeddings = get_embeddings()
    documents = [_chunk_to_document(c) for c in chunks]
    vectorstore = FAISS.from_documents(documents, embeddings)

    index_dir.mkdir(parents=True, exist_ok=True)
    vectorstore.save_local(str(index_dir))

    return len(chunks)


def load_faiss_index(index_dir: Path, embedding_model: str) -> FAISS:
    embeddings = get_embeddings()
    return FAISS.load_local(
        str(index_dir),
        embeddings,
        allow_dangerous_deserialization=True,
    )
