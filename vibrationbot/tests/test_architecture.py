"""The package layering, asserted.

The restructure that created app/chat, app/retrieval, app/ingestion and app/llm
removed two real cycles:

    services <-> graph      graph_rag_service imported five app.graph modules
                            while graph/nodes imported five app.services ones
    services <-> pipeline   index_service imported app.pipeline.index_faiss
                            while pipeline/index_faiss imported warmup_service

Neither deadlocked, because no module happened to close the loop - which is
exactly why nothing caught them. These tests fail the moment an import points
back up the stack.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent / "app"

# Lowest first. A package may import from itself or from anything BELOW it.
LAYERS: list[str] = [
    "api",
    "chat",
    "ingestion",
    "retrieval",
    "llm",
    "domain",
    "schemas",
    "config",
]
RANK = {name: i for i, name in enumerate(LAYERS)}


def _imported_packages(path: Path) -> set[str]:
    """Every app.<package> this file imports, including in-function imports."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            parts = node.module.split(".")
            if parts[0] == "app" and len(parts) > 1:
                found.add(parts[1])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] == "app" and len(parts) > 1:
                    found.add(parts[1])
    return found


def _source_files() -> list[Path]:
    return [p for p in APP.rglob("*.py") if "__pycache__" not in p.parts]


def _owning_package(path: Path) -> str | None:
    rel = path.relative_to(APP).parts
    return rel[0] if len(rel) > 1 and rel[0] in RANK else None


@pytest.mark.parametrize("path", _source_files(), ids=lambda p: str(p.name))
def test_no_upward_or_cyclic_imports(path: Path) -> None:
    src = _owning_package(path)
    if src is None:  # main.py and app/__init__.py may import anything
        return
    for dst in _imported_packages(path):
        if dst == src or dst not in RANK:
            continue
        assert RANK[dst] > RANK[src], (
            f"{path.relative_to(APP)} imports app.{dst}, but {src!r} sits below "
            f"{dst!r} in the layering. Allowed: {LAYERS[RANK[src] + 1:]}"
        )


def test_domain_stays_free_of_frameworks() -> None:
    """The domain layer computes; it must not reach for a model or a vector store."""
    banned = re.compile(r"\b(langchain|langgraph|openai|faiss|sentence_transformers)\b")
    for path in (APP / "domain").rglob("*.py"):
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith(("import ", "from ")) and banned.search(line):
                pytest.fail(f"{path.relative_to(APP)}:{i} imports a framework: {line.strip()}")


def test_every_package_is_declared_in_the_layering() -> None:
    """A new top-level package must be placed in LAYERS deliberately, not by default."""
    on_disk = {
        p.name
        for p in APP.iterdir()
        if p.is_dir() and p.name != "__pycache__" and (p / "__init__.py").exists()
    }
    assert on_disk == set(LAYERS), (
        f"packages on disk {sorted(on_disk)} != declared layering {sorted(LAYERS)}. "
        "Add the new package to LAYERS at the right depth."
    )
