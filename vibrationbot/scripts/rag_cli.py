"""
Command-line interface for the multimodal RAG (ingest + query, no server needed).

INGEST a PDF/DOCX file, or a whole folder:
    python scripts/rag_cli.py ingest "ISO 10816-3-2009.pdf"
    python scripts/rag_cli.py ingest Cat2.pdf --title "Catalogue 2"
    python scripts/rag_cli.py ingest Input_Data                 # every PDF/DOCX in the folder

ASK the multimodal agent (uses semantic + table search, figures, and vision):
    python scripts/rag_cli.py ask "What are the ISO 10816 vibration severity limits?"
    python scripts/rag_cli.py ask "show the bearing dimension table" --doc cat2
    python scripts/rag_cli.py ask "..." --simple                 # non-agentic RAG
    python scripts/rag_cli.py ask "..." --top-k 8

INTERACTIVE chat (keeps conversation history in one session):
    python scripts/rag_cli.py chat
    python scripts/rag_cli.py chat --doc cat2

LIST indexed documents:
    python scripts/rag_cli.py list
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import DEFAULT_TOP_K, SUPPORTED_EXTENSIONS
from app.schemas import DocumentStatus


# --------------------------------------------------------------------------
# ingest
# --------------------------------------------------------------------------


def _sources_line(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(
            p for p in path.iterdir() if p.suffix.lower() in SUPPORTED_EXTENSIONS
        )
    return [path]


def cmd_ingest(args: argparse.Namespace) -> int:
    from app.ingestion import ingest_service
    from app.ingestion.ingest_service import IngestBusyError
    from app.retrieval.embeddings import preload_embedding_model

    target = Path(args.path)
    if not target.is_absolute():
        target = ROOT / target
    if not target.exists():
        print(f"Not found: {target}")
        return 1

    files = _sources_line(target)
    files = [f for f in files if f.suffix.lower() in SUPPORTED_EXTENSIONS]
    if not files:
        print(f"No PDF/DOCX files in {target}")
        return 1

    print(f"Warming up embedding model ...", flush=True)
    preload_embedding_model()

    ok = 0
    for i, f in enumerate(files, start=1):
        print(f"\n[{i}/{len(files)}] Ingesting {f.name} ({f.stat().st_size/1e6:.1f} MB) ...", flush=True)
        title = args.title if (args.title and len(files) == 1) else None
        try:
            result = ingest_service.process_document_upload(
                f.read_bytes(), f.name, title=title, doc_id=args.doc_id if len(files) == 1 else None
            )
        except IngestBusyError as exc:
            print(f"  {exc}")
            return 1
        if result["status"] == DocumentStatus.READY:
            extra = f", pdf_kind={result['pdf_kind']}" if result.get("pdf_kind") else ""
            print(f"  OK: doc_id={result['doc_id']}  chunks={result['chunk_count']}{extra}")
            ok += 1
        else:
            print(f"  FAILED: {result.get('error', 'unknown error')}")

    print(f"\nDone. {ok}/{len(files)} ingested.")
    return 0 if ok == len(files) else 1


# --------------------------------------------------------------------------
# ask / chat
# --------------------------------------------------------------------------

_TYPE_TAG = {
    "table": "TABLE",
    "image": "FIGURE",
    "diagram": "FIGURE",
    "chapter_summary": "chapter",
    "section_summary": "section",
    "clause": "text",
}


def _print_response(resp) -> None:
    print("\n" + "=" * 70)
    print(resp.answer.strip())
    print("=" * 70)
    if not resp.sources:
        print("(no sources)")
        return
    print(f"Sources ({len(resp.sources)}):")
    for i, s in enumerate(resp.sources, start=1):
        tag = _TYPE_TAG.get(s.chunk_type, s.chunk_type)
        pages = f"p.{s.page_start}" if s.page_start == s.page_end else f"pp.{s.page_start}-{s.page_end}"
        line = f"  [{i}] {tag:7} {s.doc_id} · {s.section_path[:48]} ({pages}) score={s.score:.3f}"
        print(line)
        if s.asset_url:  # a figure/chart the answer can cite visually
            print(f"        figure: {s.asset_url}")


def _answer_fn(simple: bool):
    if simple:
        from app.chat.rag_service import rag_answer

        return rag_answer
    from app.chat.agent_rag_service import agent_answer

    return agent_answer


def _ready_docs() -> list[str]:
    from app.retrieval.index_service import index_service

    return index_service.list_ready_doc_ids()


def cmd_ask(args: argparse.Namespace) -> int:
    ready = _ready_docs()
    if not ready:
        print("No indexed documents. Ingest one first:  python scripts/rag_cli.py ingest <file>")
        return 1
    doc_ids = [args.doc] if args.doc else None
    if args.doc and args.doc not in ready:
        print(f"Document '{args.doc}' is not indexed. Available: {', '.join(ready)}")
        return 1

    fn = _answer_fn(args.simple)
    mode = "simple RAG" if args.simple else "agentic multimodal RAG"
    print(f"[{mode}] querying {doc_ids or 'all documents'} ...", flush=True)
    resp = fn(question=args.question, doc_ids=doc_ids, top_k=args.top_k)
    _print_response(resp)
    return 0


def cmd_chat(args: argparse.Namespace) -> int:
    ready = _ready_docs()
    if not ready:
        print("No indexed documents. Ingest one first:  python scripts/rag_cli.py ingest <file>")
        return 1
    doc_ids = [args.doc] if args.doc else None
    fn = _answer_fn(args.simple)
    session_id = None
    print(f"Multimodal RAG chat over {doc_ids or 'all documents'}.  Ctrl-C or 'exit' to quit.\n")
    while True:
        try:
            q = input("you › ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q:
            continue
        if q.lower() in ("exit", "quit", ":q"):
            break
        try:
            resp = fn(question=q, session_id=session_id, doc_ids=doc_ids, top_k=args.top_k)
            session_id = resp.session_id  # keep history across turns
            _print_response(resp)
            print()
        except Exception as exc:  # noqa: BLE001 — keep the REPL alive
            print(f"  error: {exc}\n")
    return 0


# --------------------------------------------------------------------------
# list
# --------------------------------------------------------------------------


def cmd_list(_args: argparse.Namespace) -> int:
    from app.ingestion import ingest_service

    docs = ingest_service.list_documents()
    if not docs:
        print("No documents ingested yet.")
        return 0
    print(f"{len(docs)} document(s):")
    for d in docs:
        status = getattr(d["status"], "value", d["status"])
        print(
            f"  {d['doc_id']:52} {status:10} "
            f"chunks={d['chunk_count']:<6} index={d['index_status']}"
        )
    return 0


# --------------------------------------------------------------------------
# entrypoint
# --------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="rag_cli",
        description="Multimodal RAG command-line interface (ingest + query).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_ing = sub.add_parser("ingest", help="Ingest a PDF/DOCX file or a folder")
    p_ing.add_argument("path", help="Path to a .pdf/.docx file, or a folder of them")
    p_ing.add_argument("--title", help="Title (single-file ingest only)")
    p_ing.add_argument("--doc-id", help="Force a doc_id (single-file ingest only)")
    p_ing.set_defaults(func=cmd_ingest)

    p_ask = sub.add_parser("ask", help="Ask one question")
    p_ask.add_argument("question", help="The question to ask")
    p_ask.add_argument("--doc", help="Restrict to one doc_id (default: all)")
    p_ask.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Sources to retrieve")
    p_ask.add_argument("--simple", action="store_true", help="Non-agentic RAG (one LLM call)")
    p_ask.set_defaults(func=cmd_ask)

    p_chat = sub.add_parser("chat", help="Interactive multi-turn chat")
    p_chat.add_argument("--doc", help="Restrict to one doc_id (default: all)")
    p_chat.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Sources to retrieve")
    p_chat.add_argument("--simple", action="store_true", help="Non-agentic RAG")
    p_chat.set_defaults(func=cmd_chat)

    p_list = sub.add_parser("list", help="List indexed documents")
    p_list.set_defaults(func=cmd_list)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
