"""Re-index existing documents through the current pipeline.

Re-running the pipeline re-runs vision enrichment, so figures, charts,
diagrams, and tables in documents that were ingested while vision was off get
captioned/transcribed into the knowledge base. It re-extracts, re-captions, and
re-embeds — captions are baked into chunk text before embedding, so a full
re-index is required (there is no caption-only shortcut).

Usage:
  python scripts/reindex_all.py                 # every document
  python scripts/reindex_all.py DOC_ID [...]    # only the named documents
  python scripts/reindex_all.py --list          # list documents, do nothing

Cost note: each figure/table becomes one OpenAI vision call, and every document
is fully re-embedded. Target specific docs to avoid reprocessing duplicates.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import (
    DOCUMENTS_DIR,
    ENABLE_VISION_ENRICHMENT,
    VISION_MODEL,
)
from app.ingestion import ingest_service


def _find_source(doc_dir: Path) -> Path | None:
    for name in ("source.pdf", "source.docx"):
        p = doc_dir / name
        if p.exists():
            return p
    return None


def _doc_dirs() -> list[Path]:
    if not DOCUMENTS_DIR.exists():
        return []
    return [d for d in sorted(DOCUMENTS_DIR.iterdir()) if d.is_dir()]


def _title_for(doc_dir: Path) -> str:
    reg = doc_dir / "document_registry.json"
    if reg.exists():
        try:
            return json.loads(reg.read_text(encoding="utf-8")).get("title", doc_dir.name)
        except Exception:
            pass
    return doc_dir.name


def main(argv: list[str]) -> int:
    flags = {a for a in argv if a.startswith("-")}
    requested = [a for a in argv if not a.startswith("-")]

    docs = _doc_dirs()
    if not docs:
        print("No documents found under", DOCUMENTS_DIR)
        return 1

    if "--list" in flags:
        print(f"{len(docs)} document(s):")
        for d in docs:
            src = _find_source(d)
            assets = len(list((d / "assets").glob("*"))) if (d / "assets").exists() else 0
            print(f"  {d.name:52} {src.name if src else '(no source)':12} assets={assets}")
        return 0

    known = {d.name for d in docs}
    for missing in [r for r in requested if r not in known]:
        print(f"Unknown doc_id (ignored): {missing}")
    targets = [d for d in docs if not requested or d.name in requested]
    if not targets:
        print("Nothing to do. Use --list to see available documents.")
        return 1

    if ENABLE_VISION_ENRICHMENT:
        print(f"Vision enrichment: ON  (model={VISION_MODEL})")
    else:
        print(
            "Vision enrichment: OFF — set ENABLE_VISION_ENRICHMENT=true in .env "
            "to caption figures/tables."
        )
    print(f"Re-indexing {len(targets)} document(s):\n")

    ok = 0
    for d in targets:
        src = _find_source(d)
        if not src:
            print(f"  {d.name}: SKIP (no source file)")
            continue
        print(f"  {d.name}: re-indexing from {src.name} ...", flush=True)
        # Reuse the canonical ingest path: it invalidates caches, writes
        # status.json (with chunk_count + enriched count), patches the registry,
        # and reloads the index — keeping re-index behaviour identical to upload.
        ingest_service.run_pipeline_job(d.name, src, _title_for(d))

        try:
            status = json.loads((d / "status.json").read_text(encoding="utf-8"))
        except Exception:
            status = {}
        if status.get("status") == "ready":
            print(
                f"    OK: {status.get('chunk_count', '?')} chunks, "
                f"{status.get('enriched_figures', 0)} visual element(s) enriched"
            )
            ok += 1
        else:
            print(f"    FAILED: {status.get('error', 'unknown error')}")

    print(f"\nDone. {ok}/{len(targets)} re-indexed.")
    return 0 if ok == len(targets) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
