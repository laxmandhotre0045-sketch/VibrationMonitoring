"""
Ingest all PDF/DOCX files from a folder with step-by-step terminal output.

Usage:
    python scripts/ingest_folder.py Input_Data
    python scripts/ingest_folder.py Input_Data --pattern "*.pdf"
"""

from __future__ import annotations

import argparse
import sys
import time
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Parse --light before importing app (so env vars apply to Docling config)
if "--light" in sys.argv:
    os.environ["DOCLING_LIGHT_MODE"] = "true"
    os.environ["DOCLING_DO_OCR"] = "false"

from app.config import DOCUMENTS_DIR, SUPPORTED_EXTENSIONS
from app.schemas import DocumentStatus
from app.ingestion.progress import banner, error, step, success, summary
from app.ingestion import ingest_service
from app.retrieval.index_service import index_service
from app.retrieval.embeddings import preload_embedding_model


def _collect_files(folder: Path, pattern: str) -> list[Path]:
    files = sorted(folder.glob(pattern))
    return [f for f in files if f.suffix.lower() in SUPPORTED_EXTENSIONS and f.is_file()]


def ingest_file(file_path: Path, file_num: int, total_files: int) -> dict:
    banner(f"Document {file_num}/{total_files}: {file_path.name}")

    step(0, 3, f"Saving source file ...", doc_id=file_path.stem)
    content = file_path.read_bytes()
    size_mb = len(content) / (1024 * 1024)
    step(0, 3, f"File size: {size_mb:.1f} MB")

    step(1, 3, "Running full pipeline (extract → enrich → index) ...")
    t0 = time.perf_counter()
    result = ingest_service.process_document_upload(
        content,
        file_path.name,
        title=file_path.stem.replace("_", " ").replace("-", " ").title(),
    )
    elapsed = time.perf_counter() - t0

    if result["status"] == DocumentStatus.READY:
        step(2, 3, f"Indexed in {elapsed:.1f}s — doc_id={result['doc_id']}")
        success(f"{file_path.name} → {result['doc_id']} ({result['chunk_count']} chunks)")
    else:
        error(f"{file_path.name} FAILED: {result.get('error', 'unknown error')}")

    return {**result, "elapsed_s": round(elapsed, 1), "file": file_path.name}


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest documents from a folder")
    parser.add_argument(
        "folder",
        nargs="?",
        default="Input_Data",
        help="Folder containing PDF/DOCX files (default: Input_Data)",
    )
    parser.add_argument(
        "--pattern",
        default="*",
        help='Glob pattern within folder (default: "*")',
    )
    parser.add_argument(
        "--light",
        action="store_true",
        help="Force light extraction (no OCR, lower memory) for all PDFs",
    )
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.is_absolute():
        folder = ROOT / folder

    if not folder.exists():
        error(f"Folder not found: {folder}")
        return 1

    files = _collect_files(folder, args.pattern)
    if not files:
        error(f"No PDF/DOCX files found in {folder}")
        return 1

    banner(f"Ingesting {len(files)} file(s) from {folder}")
    print(f"Output directory: {DOCUMENTS_DIR}\n", flush=True)

    step(0, 1, "Warming up embedding model ...")
    preload_embedding_model()
    success("Embedding model ready")

    results: list[dict] = []
    for i, file_path in enumerate(files, start=1):
        try:
            results.append(ingest_file(file_path, i, len(files)))
        except Exception as exc:
            error(f"{file_path.name}: {exc}")
            results.append(
                {
                    "file": file_path.name,
                    "status": DocumentStatus.FAILED,
                    "error": str(exc),
                }
            )

    ready = [r for r in results if r.get("status") == DocumentStatus.READY]
    failed = [r for r in results if r.get("status") != DocumentStatus.READY]

    banner("Ingestion complete")
    summary(
        [
            ("Total files", str(len(files))),
            ("Succeeded", str(len(ready))),
            ("Failed", str(len(failed))),
            ("Ready documents", ", ".join(r["doc_id"] for r in ready) or "none"),
        ]
    )

    if ready:
        print("\nYou can now chat at http://127.0.0.1:8000/\n", flush=True)
        print("List documents:", flush=True)
        for doc in ingest_service.list_documents():
            if doc["status"] == DocumentStatus.READY:
                print(
                    f"  • {doc['doc_id']} — {doc['title']} ({doc['chunk_count']} chunks)",
                    flush=True,
                )

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
