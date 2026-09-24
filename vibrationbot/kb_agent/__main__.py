"""Command line access to the knowledge-base agent.

    python -m kb_agent docs
    python -m kb_agent search "ball pass frequency outer race"
    python -m kb_agent ask "what causes oil whirl in journal bearings?"
    python -m kb_agent passage condition_monitoring chunk_000412

Everything the agent can do is reachable from here. If the CLI and a calling
agent disagree, the agent is wrong -- both go through the same
``KnowledgeBaseAgent`` methods, so this doubles as the smoke test for a
deployment.

``docs`` and ``search`` call no model, so they work with no API key and cost
nothing. Use them to check what is in the corpus before spending a request.

Output is forced to ASCII by ``_ascii``, and that is not cosmetic. A Windows
console defaults to cp1252, and the corpus is full of characters it cannot
encode: em dashes, the degree sign, and -- worse -- private-use glyphs such as
U+F0E3 that scanned PDFs carry over from symbol fonts. Printing raw book text
raises UnicodeEncodeError and turns a working query into a traceback.
"""

from __future__ import annotations

import argparse
import sys
import textwrap
import unicodedata

from kb_agent.agent import AgentResult, KnowledgeBaseAgent
from kb_agent.config import KB_MAX_ITERATIONS, KB_TOP_K

WIDTH = 96

#: Typography the books use constantly, mapped to what a cp1252 console can
#: print. Everything not listed falls through to the decomposition pass below.
_TRANSLIT = {
    "—": "-", "–": "-", "‒": "-", "−": "-",
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"',
    "…": "...", "×": "x", "÷": "/",
    "°": " deg", "µ": "u", "μ": "u",
    "≠": "!=", "≤": "<=", "≥": ">=", "±": "+/-",
    "√": "sqrt", "π": "pi", "ω": "omega", "Δ": "delta",
    "→": "->", "•": "*", " ": " ",
}


def _ascii(text: str) -> str:
    """Make any document or model text safe for a cp1252 console.

    Three passes, cheapest first: translate the punctuation the books actually
    use, decompose accented letters to their base form, then drop whatever is
    left. The final drop is what handles private-use glyphs -- they carry no
    meaning outside the PDF's own font, so losing them costs nothing.
    """
    if not text:
        return ""
    out = "".join(_TRANSLIT.get(ch, ch) for ch in text)
    out = unicodedata.normalize("NFKD", out)
    return out.encode("ascii", "ignore").decode("ascii")


def _rule(char: str = "-") -> str:
    return char * WIDTH


def _wrap(text: str, indent: str = "    ") -> str:
    out: list[str] = []
    for para in _ascii(text).split("\n"):
        if not para.strip():
            out.append("")
            continue
        out.extend(
            textwrap.wrap(
                para.strip(),
                width=WIDTH - len(indent),
                initial_indent=indent,
                subsequent_indent=indent,
            )
        )
    return "\n".join(out)


def _print_documents(result: AgentResult) -> None:
    docs = result.data
    if not docs:
        print("No documents are indexed.")
        print("\nIngest one with:")
        print("    python scripts/ingest_folder.py <folder-of-pdfs>")
        return
    print(f"{len(docs)} document(s) indexed, {result.meta['total_chunks']} chunks total:\n")
    for d in docs:
        print(f"  {d['doc_id']}")
        print(f"    title   : {_ascii(d['title'])}")
        print(f"    source  : {_ascii(d['source_file'])}")
        print(f"    chunks  : {d['chunk_count']}   figures captioned: {d['enriched_figures']}")
        if d["pdf_kind"]:
            print(f"    pdf kind: {d['pdf_kind']}")
        print()


def _print_passages(result: AgentResult, *, full: bool, limit: int) -> None:
    passages = result.data[:limit] if limit else result.data
    if not passages:
        print("No excerpts matched.")
        print("\nTry: different wording, textbook vocabulary, or a broader query.")
        return
    m = result.meta
    if m.get("query"):
        print(f"query    : {_ascii(m['query'])}")
        print(f"documents: {', '.join(m['documents_searched'])}")
        print(f"found    : {len(result.data)} excerpt(s) in {m.get('elapsed_ms', 0)} ms")
        print()
    for p in passages:
        print(f"  [{p['label']}] rerank {p['score']:<9} {p['chunk_type']}")
        print(f"      {_ascii(p['citation'])[:WIDTH - 6]}")
        print(f"      chunk_id: {p['chunk_id']}")
        text = p["text"] if full else (p["text"][:400] + ("..." if len(p["text"]) > 400 else ""))
        print(_wrap(text, indent="      "))
        print()


def _print_answer(result: AgentResult, *, show_trace: bool, sources: int) -> None:
    m = result.meta
    print(_rule("="))
    print(_wrap(m["question"], indent="  Q: ")[:WIDTH * 4])
    print(_rule("="))
    print()
    print(_wrap(m.get("answer", ""), indent="  "))
    print()

    cited = m.get("cited_labels") or []
    print(_rule())
    print(
        f"  searched {len(m.get('documents_searched', []))} document(s) | "
        f"{m.get('searches_run', 0)} search(es) | "
        f"{m.get('iterations', 0)} iteration(s) | "
        f"{m.get('elapsed_ms', 0)} ms"
    )
    if not cited and result.data:
        print("  WARNING: the answer cited no excerpt. Treat it as ungrounded.")
    print(_rule())

    if m.get("searches"):
        print("\n  Searches the agent ran:")
        for s in m["searches"]:
            print(f"    - {_ascii(s)}")

    shown = [p for p in result.data if p["label"] in cited] or result.data
    if sources:
        print(f"\n  Sources ({len(shown)} of {len(result.data)} excerpts):")
        for p in shown[:sources]:
            marker = "*" if p["label"] in cited else " "
            print(f"  {marker} [{p['label']}] {_ascii(p['citation'])[:WIDTH - 8]}")
            print(_wrap(p["text"][:300] + ("..." if len(p["text"]) > 300 else ""), indent="        "))

    if show_trace and m.get("trace"):
        print("\n  Trace:")
        for step in m["trace"]:
            ms = f"{step.get('ms', 0):>6} ms" if "ms" in step else " " * 9
            print(f"    {ms}  {step['step']:<22} {_ascii(str(step.get('detail', '')))}")

    print("\n  Caveats:")
    for c in m.get("caveats", []):
        print(_wrap(f"- {c}", indent="    "))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m kb_agent",
        description="Query the indexed vibration standards and textbooks.",
    )
    parser.add_argument(
        "--json", action="store_true", help="Print the raw result envelope as JSON."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("docs", help="List the indexed documents")

    p_search = sub.add_parser(
        "search", help="Raw retrieval, no model call (needs no API key)"
    )
    p_search.add_argument("query", help="What to search for")
    p_search.add_argument(
        "--doc", action="append", dest="docs", help="Restrict to a doc_id (repeatable)"
    )
    p_search.add_argument("--top-k", type=int, default=KB_TOP_K, help=f"Excerpts (default {KB_TOP_K})")
    p_search.add_argument(
        "--type",
        action="append",
        dest="types",
        choices=["clause", "table", "image", "diagram"],
        help="Restrict to a chunk type (repeatable)",
    )
    p_search.add_argument("--full", action="store_true", help="Print untruncated passage text")
    p_search.add_argument("--limit", type=int, default=0, help="Print only the first N")

    p_ask = sub.add_parser("ask", help="Ask a question and get a cited answer")
    p_ask.add_argument("question", help="The question, in quotes")
    p_ask.add_argument(
        "--doc", action="append", dest="docs", help="Restrict to a doc_id (repeatable)"
    )
    p_ask.add_argument("--top-k", type=int, default=KB_TOP_K, help=f"Excerpts per search (default {KB_TOP_K})")
    p_ask.add_argument(
        "--max-iterations",
        type=int,
        default=KB_MAX_ITERATIONS,
        help=f"Tool-loop bound (default {KB_MAX_ITERATIONS})",
    )
    p_ask.add_argument("--trace", action="store_true", help="Show every model and tool call")
    p_ask.add_argument(
        "--verify",
        action="store_true",
        help="Print a verification sheet: every claim beside the book text behind it",
    )
    p_ask.add_argument(
        "--save", metavar="PATH", help="Write the verification sheet to a file"
    )
    p_ask.add_argument(
        "--sources", type=int, default=6, help="Source excerpts to print (0 for none)"
    )

    p_passage = sub.add_parser("passage", help="Print one passage in full, by id")
    p_passage.add_argument("doc_id")
    p_passage.add_argument("chunk_id")

    sub.add_parser("check", help="Verify the corpus and the model are both reachable")

    args = parser.parse_args(argv)
    agent = KnowledgeBaseAgent()

    if args.command == "check":
        docs = agent.documents()
        if not docs.ok:
            print(f"corpus : FAILED - {docs.error}", file=sys.stderr)
            return 1
        print(f"corpus : OK - {docs.meta['count']} document(s), {docs.meta['total_chunks']} chunks")
        if not docs.data:
            print("model  : SKIPPED - nothing indexed to search")
            return 1
        probe = agent.search("vibration", top_k=1)
        print(
            f"search : {'OK' if probe.ok else 'FAILED'}"
            + (f" - {len(probe.data)} hit in {probe.meta.get('elapsed_ms')} ms" if probe.ok else f" - {probe.error}")
        )
        answer = agent.ask("What is this document about?", max_iterations=1)
        if answer.ok:
            print(f"model  : OK - answered in {answer.meta.get('elapsed_ms')} ms")
            return 0
        print(f"model  : FAILED - {answer.error}", file=sys.stderr)
        return 1

    if args.command == "docs":
        result = agent.documents()
    elif args.command == "search":
        result = agent.search(
            args.query, doc_ids=args.docs, top_k=args.top_k, chunk_types=args.types
        )
    elif args.command == "passage":
        result = agent.passage(args.doc_id, args.chunk_id)
    else:
        result = agent.ask(
            args.question,
            doc_ids=args.docs,
            top_k=args.top_k,
            max_iterations=args.max_iterations,
        )

    if args.json:
        print(result.to_json(indent=2))
        return 0 if result.ok else 1

    if not result.ok:
        # Errors to stderr so `... --json > file` keeps the file clean and a
        # shell pipeline can still see what went wrong.
        print(f"Error: {result.error}", file=sys.stderr)
        return 1

    if result.kind == "kb_documents":
        _print_documents(result)
    elif result.kind == "kb_search":
        _print_passages(result, full=args.full, limit=args.limit)
    elif result.kind == "kb_passage":
        _print_passages(result, full=True, limit=0)
    else:
        if getattr(args, "verify", False) or getattr(args, "save", None):
            from kb_agent.verify import build_report

            report = build_report(result)
            if getattr(args, "save", None):
                # utf-8 on disk; the console print stays ASCII-safe.
                with open(args.save, "w", encoding="utf-8") as fh:
                    fh.write(report)
                print(f"Verification sheet written to {args.save}")
                print()
            if getattr(args, "verify", False):
                print(_ascii(report))
                return 0
        _print_answer(result, show_trace=args.trace, sources=args.sources)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
