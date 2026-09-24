"""Embedding/reranker models and the retrieval candidate budgets."""

import os as _os

EMBEDDING_MODEL = _os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
RERANKER_MODEL = _os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")

DEFAULT_TOP_K = int(_os.getenv("DEFAULT_TOP_K", "6"))

RETRIEVAL_CANDIDATE_K = int(_os.getenv("RETRIEVAL_CANDIDATE_K", "30"))
# Candidates are pulled *per document index*, so the merged pool grows linearly
# with the corpus: 8 documents x 30 = 240, of which the reranker only ever sees
# RERANK_POOL_K. Past RETRIEVAL_MULTI_DOC_THRESHOLD indexes the per-index number
# drops, keeping the merged pool near the rerank budget instead of discarding
# most of it on the crude hybrid score alone.
RETRIEVAL_CANDIDATE_K_MULTI = int(_os.getenv("RETRIEVAL_CANDIDATE_K_MULTI", "15"))
RETRIEVAL_MULTI_DOC_THRESHOLD = int(_os.getenv("RETRIEVAL_MULTI_DOC_THRESHOLD", "3"))
# Candidates fed to the cross-encoder reranker, after merging across documents.
RERANK_POOL_K = int(_os.getenv("RERANK_POOL_K", "48"))
