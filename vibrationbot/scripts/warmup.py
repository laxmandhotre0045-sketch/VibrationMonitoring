"""
Pre-download and load the embedding model before first upload or chat.

Usage:
    .venv\\Scripts\\python scripts\\warmup.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import EMBEDDING_MODEL
from app.retrieval.embeddings import preload_embedding_model


def main() -> None:
    print(f"Pre-downloading embedding model: {EMBEDDING_MODEL}")
    preload_embedding_model()
    print("Done. Model is cached and ready.")


if __name__ == "__main__":
    main()
