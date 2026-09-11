#!/usr/bin/env python
"""Run one agent from the terminal, and prove it touched nothing else.

    python run_agent.py list
    python run_agent.py iso    "zone B/C for a 55 kW pump, separate driver, rigid"
    python run_agent.py sql    data "cooling water pump"
    python run_agent.py report build "cooling water pump" --separate-driver
    python run_agent.py kb --with-books ask "what causes oil whirl"

Three things this does that running ``python -m <agent>`` does not.

**It loads only the agent asked for.** Imports happen after the agent is
chosen, so asking the SQL agent a question does not drag in faiss, the
embedding model or the 13,059-chunk book index. That is most of the start-up
cost, and it is the difference between a two-second answer and a thirty-second
one.

**It checks the isolation rather than asserting it.** Each agent declares the
paths it may write. Before the run every *other* agent's paths are fingerprinted
-- file count, total bytes, newest mtime -- and afterwards they are compared. If
a run modified something belonging to another agent, this says so. A guarantee
that is only a comment in a docstring is not a guarantee.

**The books are opt-in.** ``kb`` needs ``--with-books`` before it will start,
because it is the one agent that loads the document index and calls a paid API.
Everything else here runs on platform data alone, offline where it can.
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

#: The model every agent in this runner uses unless the environment already
#: says otherwise. Set here rather than in each agent so one edit moves them
#: all, and so a run cannot silently cost more than the last one.
DEFAULT_MODEL = "gpt-4o-mini"


@dataclass(frozen=True)
class AgentSpec:
    """One agent, and what it is allowed to touch."""

    name: str
    module: str
    summary: str
    #: Directories this agent may write to. Everything else is another agent's,
    #: and is checked for accidental modification after the run.
    writes: tuple[str, ...] = ()
    #: Agents this one legitimately builds on. Loading these is expected;
    #: anything else appearing is a leak worth knowing about.
    depends_on: tuple[str, ...] = ()
    #: Loads the document index and calls a paid API. Opt-in.
    needs_books: bool = False
    #: Runs with no network and no key at all.
    offline: bool = False
    example: str = ""


AGENTS: dict[str, AgentSpec] = {
    "iso": AgentSpec(
        name="iso",
        module="iso_agent",
        summary="ISO 10816-3 severity limits, looked up from unit-tested tables",
        writes=(),  # reads a JSON table, writes nothing at all
        offline=True,
        example='run_agent.py iso "zone B/C for a 55 kW pump, separate driver, rigid"',
    ),
    "sql": AgentSpec(
        name="sql",
        module="sql_agent",
        summary="Pull sensor, capture and feature rows from the platform API",
        writes=("data/exports",),
        example='run_agent.py sql data "cooling water pump"',
    ),
    "report": AgentSpec(
        name="report",
        module="report_agent",
        summary="Build a condition report with a provenance ledger and verifier",
        writes=(),  # writes only where --out points, chosen by the caller
        depends_on=("sql_agent",),  # reads its rows through the SQL agent
        example='run_agent.py report build "cooling water pump" --separate-driver',
    ),
    "kb": AgentSpec(
        name="kb",
        module="kb_agent",
        summary="Answer from the indexed reference books (needs --with-books)",
        writes=("logs",),
        needs_books=True,
        example='run_agent.py kb --with-books ask "what causes oil whirl"',
    ),
}


# ----------------------------------------------------------------- isolation --


def _fingerprint(path: Path) -> tuple[int, int, float]:
    """(files, total bytes, newest mtime) for a directory tree.

    Cheap and sufficient: a write changes at least one of the three. Hashing
    contents would be stronger and far slower on a directory holding the FAISS
    indexes, and this runs on every invocation.
    """
    if not path.exists():
        return (0, 0, 0.0)
    files = 0
    total = 0
    newest = 0.0
    for entry in path.rglob("*"):
        try:
            if entry.is_file():
                stat = entry.stat()
                files += 1
                total += stat.st_size
                newest = max(newest, stat.st_mtime)
        except OSError:
            continue  # a file vanishing mid-scan is not this check's business
    return (files, total, newest)


def _other_agents_paths(chosen: AgentSpec) -> dict[str, Path]:
    """Every write path belonging to an agent other than this one."""
    out: dict[str, Path] = {}
    for spec in AGENTS.values():
        if spec.name == chosen.name:
            continue
        for rel in spec.writes:
            out[f"{spec.name}:{rel}"] = BASE_DIR / rel
    return out


# --------------------------------------------------------------------- run --


def _run(spec: AgentSpec, argv: list[str]) -> int:
    """Import the chosen agent and hand it its arguments."""
    module = importlib.import_module(f"{spec.module}.__main__")
    main = getattr(module, "main", None)
    if main is None:
        print(f"{spec.module} has no main(); cannot run it here.", file=sys.stderr)
        return 2
    return int(main(argv) or 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_agent.py",
        description="Run one agent in isolation from the others.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(f"  {s.example}" for s in AGENTS.values() if s.example),
    )
    parser.add_argument("agent", help="Which agent: " + ", ".join(AGENTS) + ", or 'list'")
    parser.add_argument("--with-books", action="store_true",
                        help="Allow the book index to load (kb only)")
    parser.add_argument("--model", default=None,
                        help=f"Model for agents that use one (default {DEFAULT_MODEL})")
    parser.add_argument("--no-isolation-check", action="store_true",
                        help="Skip the before/after check on other agents' data")
    parser.add_argument("rest", nargs=argparse.REMAINDER,
                        help="Arguments passed through to the agent")
    args = parser.parse_args(argv)

    if args.agent == "list":
        print("Agents:\n")
        for spec in AGENTS.values():
            tags = []
            if spec.offline:
                tags.append("offline")
            if spec.needs_books:
                tags.append("needs --with-books")
            suffix = f"  [{', '.join(tags)}]" if tags else ""
            print(f"  {spec.name:<8} {spec.summary}{suffix}")
            if spec.example:
                print(f"           e.g. python {spec.example}")
        return 0

    spec = AGENTS.get(args.agent)
    if spec is None:
        print(f"Unknown agent {args.agent!r}. Try: {', '.join(AGENTS)}, or 'list'.",
              file=sys.stderr)
        return 2

    if spec.needs_books and not args.with_books:
        print(
            f"The {spec.name} agent loads the document index and calls a paid API, so it is "
            "opt-in here.\nAdd --with-books if that is what you want:\n"
            f"    python {spec.example}",
            file=sys.stderr,
        )
        return 2

    # One model for every agent that uses one, set before the agent imports.
    os.environ.setdefault("OPENAI_MODEL", args.model or DEFAULT_MODEL)

    watched = {} if args.no_isolation_check else _other_agents_paths(spec)
    before = {label: _fingerprint(path) for label, path in watched.items()}

    started = time.perf_counter()
    try:
        code = _run(spec, args.rest)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    elapsed = time.perf_counter() - started

    # What actually loaded. Proof the lazy import held, not a claim about it.
    heavy = sorted(
        {m.split(".")[0] for m in sys.modules
         if m.split(".")[0] in {"faiss", "torch", "sentence_transformers", "langchain_openai"}}
    )
    loaded_agents = {
        m.split(".")[0] for m in sys.modules
        if m.split(".")[0] in {s.module for s in AGENTS.values()}
        and m.split(".")[0] != spec.module
    }
    expected = set(spec.depends_on)
    unexpected = sorted(loaded_agents - expected)
    declared = sorted(loaded_agents & expected)

    print()
    print("-" * 78)
    print(f"  agent     : {spec.name} ({spec.module})   {elapsed:.2f}s")
    print(f"  model     : {os.environ.get('OPENAI_MODEL', '-')}"
          + ("   (not used - this agent runs offline)" if spec.offline else ""))
    if heavy:
        print(f"  heavy libs: {', '.join(heavy)}")
    if declared:
        print(f"  depends on: {', '.join(declared)} (declared)")
    if unexpected:
        print(f"  UNEXPECTED: {', '.join(unexpected)} loaded but not declared as a dependency")
    elif not declared:
        print("  loaded    : this agent only - nothing else was imported")

    if watched:
        changed = [label for label, path in watched.items()
                   if _fingerprint(path) != before[label]]
        if changed:
            print(f"  ISOLATION : FAILED - this run modified {', '.join(changed)}")
        else:
            print(f"  isolation : OK - {len(watched)} other-agent path(s) unchanged")
    print("-" * 78)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
