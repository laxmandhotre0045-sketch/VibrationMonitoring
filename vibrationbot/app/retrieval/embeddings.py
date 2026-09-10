from __future__ import annotations

import logging
import threading

from app.config import EMBEDDING_MODEL

logger = logging.getLogger(__name__)

_embeddings = None
_lock = threading.Lock()
_ready = False


def _create_embeddings(model_name: str):
    if "bge" in model_name.lower():
        from langchain_community.embeddings import HuggingFaceBgeEmbeddings

        return HuggingFaceBgeEmbeddings(
            model_name=model_name,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
            query_instruction="Represent this sentence for searching relevant passages: ",
        )
    from langchain_community.embeddings import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(
        model_name=model_name,
        encode_kwargs={"normalize_embeddings": True},
    )


def preload_embedding_model(model_name: str | None = None) -> str:
    """
    Download (if needed) and load the sentence-transformers embedding model.
    Safe to call multiple times; subsequent calls return immediately.
    """
    global _embeddings, _ready

    name = model_name or EMBEDDING_MODEL

    with _lock:
        if _ready and _embeddings is not None:
            logger.info("Embedding model already loaded: %s", name)
            return name

        logger.info("Pre-downloading embedding model: %s", name)
        _embeddings = _create_embeddings(name)
        _embeddings.embed_query("warmup")
        _ready = True
        logger.info("Embedding model ready: %s", name)
        return name


def get_embeddings():
    """Return cached embeddings instance, loading on first use if needed."""
    preload_embedding_model()
    return _embeddings


def is_ready() -> bool:
    return _ready
