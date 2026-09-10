"""Retrieval over the per-document FAISS indexes.

    embeddings.py       the shared BGE embedding model, loaded once
    faiss_index.py      FAISS store adapter - build (ingest) and load (serve)
    index_service.py    caches vectorstores, chunk maps and readiness status
    retrieval_service.py  hybrid scoring, cross-document merge, dedupe, rerank

This package has no dependency on ingestion or chat: ingestion calls
``faiss_index.build_faiss_index`` on its way out, and chat reads through
``index_service`` and ``retrieve_across_documents``. Both edges point inward.
"""
