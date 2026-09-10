"""Unit tests for retrieval scoring/dedupe. No index or OpenAI required."""

import pytest
from langchain_core.documents import Document

from app.retrieval import embeddings as warmup_service, retrieval_service
from app.retrieval.retrieval_service import (
    _rerank_candidates,
    retrieve_across_documents,
)


class FakeStore:
    """Minimal stand-in for a FAISS vectorstore.

    Tracks which search path was used so tests can assert the query is
    embedded once and reused, rather than re-embedded per index.
    """

    def __init__(self, docs):
        self._docs = docs
        self.text_search_calls = 0
        self.vector_search_calls = 0

    def similarity_search_with_score(self, query, k):
        self.text_search_calls += 1
        return self._docs[:k]

    def similarity_search_with_score_by_vector(self, embedding, k):
        self.vector_search_calls += 1
        return self._docs[:k]


@pytest.fixture(autouse=True)
def fake_embeddings(monkeypatch):
    """Avoid loading the real BGE model; count embed_query calls."""

    class FakeEmbeddings:
        def __init__(self):
            self.calls = 0

        def embed_query(self, text):
            self.calls += 1
            return [0.1, 0.2, 0.3]

    fake = FakeEmbeddings()
    monkeypatch.setattr(warmup_service, "get_embeddings", lambda: fake)
    return fake


def _doc(chunk_id, doc_id, text, distance, chunk_type="clause"):
    return (
        Document(
            page_content=text,
            metadata={
                "chunk_id": chunk_id,
                "doc_id": doc_id,
                "chunk_type": chunk_type,
                "page_start": 1,
                "page_end": 1,
                "section_path": "S",
                "node_id": "n",
            },
        ),
        distance,
    )


def _no_reranker(monkeypatch):
    """Force the hybrid-score path so ordering is deterministic."""
    monkeypatch.setattr(
        retrieval_service, "_get_reranker", lambda: (_ for _ in ()).throw(RuntimeError("off"))
    )


def test_cross_doc_chunk_id_collision_is_not_dropped(monkeypatch):
    """chunk_id restarts per document; identical ids must not collapse."""
    _no_reranker(monkeypatch)
    indexes = {
        "docA": FakeStore([_doc("chunk_000001", "docA", "alpha content here", 0.1)]),
        "docB": FakeStore([_doc("chunk_000001", "docB", "beta content here", 0.2)]),
    }
    results = retrieve_across_documents(indexes, "content", top_k=6)
    assert len(results) == 2
    assert {r["doc_id"] for r in results} == {"docA", "docB"}


def test_identical_text_across_docs_is_collapsed(monkeypatch):
    """Re-uploaded/duplicate documents must not consume multiple slots."""
    _no_reranker(monkeypatch)
    indexes = {
        "docA": FakeStore([_doc("chunk_000001", "docA", "Same Passage.", 0.1)]),
        "docB": FakeStore([_doc("chunk_000009", "docB", "same   passage.", 0.3)]),
    }
    results = retrieve_across_documents(indexes, "passage", top_k=6)
    assert len(results) == 1
    # The better-scoring copy survives.
    assert results[0]["doc_id"] == "docA"


def test_scores_stay_on_one_scale_across_documents(monkeypatch):
    """Reranking happens once on the merged pool, never per-document."""
    calls = []

    class FakeReranker:
        def predict(self, pairs):
            calls.append(len(pairs))
            return [float(len(pairs) - i) for i in range(len(pairs))]

    monkeypatch.setattr(retrieval_service, "_get_reranker", lambda: FakeReranker())

    indexes = {
        f"doc{i}": FakeStore(
            [_doc(f"chunk_00000{j}", f"doc{i}", f"text {i}{j}", 0.1 * j) for j in range(5)]
        )
        for i in range(3)
    }
    results = retrieve_across_documents(indexes, "text", top_k=4)

    assert len(calls) == 1, f"reranker ran {len(calls)}x; must run once on merged pool"
    assert calls[0] == 15, "reranker should see candidates from all 3 documents"
    assert len(results) == 4
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_query_is_embedded_once_across_documents(monkeypatch, fake_embeddings):
    """Regression: the query was re-embedded once per document index."""
    _no_reranker(monkeypatch)
    stores = {
        f"doc{i}": FakeStore([_doc(f"chunk_00000{i}", f"doc{i}", f"text {i}", 0.1)])
        for i in range(4)
    }
    retrieve_across_documents(stores, "a query", top_k=6)

    assert fake_embeddings.calls == 1, "query should be embedded exactly once"
    for store in stores.values():
        assert store.vector_search_calls == 1
        assert store.text_search_calls == 0


def test_single_document_skips_pre_embedding(fake_embeddings, monkeypatch):
    """With one index there is nothing to amortize; keep the simple path."""
    _no_reranker(monkeypatch)
    store = FakeStore([_doc("chunk_000001", "docA", "only text", 0.1)])
    retrieve_across_documents({"docA": store}, "a query", top_k=6)

    assert fake_embeddings.calls == 0
    assert store.text_search_calls == 1


def test_rerank_failure_preserves_hybrid_ordering(monkeypatch):
    _no_reranker(monkeypatch)
    candidates = [
        {"text": f"t{i}", "score": 1.0 - i / 10, "hybrid_score": 1.0 - i / 10}
        for i in range(10)
    ]
    out = _rerank_candidates("q", candidates, top_k=3)
    assert len(out) == 3
    assert [c["text"] for c in out] == ["t0", "t1", "t2"]


def test_rerank_pool_not_truncated_below_candidate_k(monkeypatch):
    """Regression: the pool was hardcoded to 20, below RETRIEVAL_CANDIDATE_K=30."""
    seen = []

    class FakeReranker:
        def predict(self, pairs):
            seen.append(len(pairs))
            return [0.0] * len(pairs)

    monkeypatch.setattr(retrieval_service, "_get_reranker", lambda: FakeReranker())
    candidates = [
        {"text": f"t{i}", "score": 0.5, "hybrid_score": 0.5} for i in range(30)
    ]
    _rerank_candidates("q", candidates, top_k=6)
    assert seen[0] == 30
