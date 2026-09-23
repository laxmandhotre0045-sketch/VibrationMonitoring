"""vibcore must depend on neither service — VIK-035.

The package exists so the platform and the chatbot cannot reach different
answers about the same bearing. That only holds while it is genuinely
shared, and the way a shared package stops being shared is one import: a
convenience reference to `app.something` from whichever service the author
happened to be working in that day. The other service then cannot import it
at all, or worse, imports it and gets that service's configuration.

It is a one-line mistake and an easy one, because in the backend `vibcore`
and `app` sit side by side and both are importable. Nothing about the layout
stops it. This does.

The second rule is about weight rather than correctness. `vibcore` is
arithmetic and three JSON tables. Both services inherit whatever it depends
on, and a dependency added here to save a few lines is paid for twice --
once in the chatbot's already large environment, and once in the platform's
Docker image. numpy is allowed because the platform has it regardless and
the maths may genuinely want it; anything else should be a deliberate
decision rather than a drive-by import.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

VIBCORE = Path(__file__).resolve().parents[1] / "vibcore"

#: Third-party packages vibcore may import. Everything in the standard
#: library is fine and is not listed.
ALLOWED_THIRD_PARTY = frozenset({"numpy"})

#: Anything importable only inside one service.
FORBIDDEN_ROOTS = frozenset({"app", "tests", "alembic", "scripts"})

STDLIB_HINT = frozenset({
    "__future__", "abc", "argparse", "ast", "bisect", "collections", "copy",
    "csv", "dataclasses", "datetime", "decimal", "enum", "functools",
    "hashlib", "io", "itertools", "json", "logging", "math", "os",
    "pathlib", "re", "statistics", "string", "sys", "textwrap", "threading",
    "time", "typing", "unicodedata", "uuid", "warnings",
})


def modules() -> list[Path]:
    found = sorted(VIBCORE.glob("*.py"))
    assert found, f"no modules found in {VIBCORE}"
    return found


def imported_roots(path: Path) -> set[str]:
    """Every top-level package this file imports, in-function ones included.

    Walking the tree rather than reading the header, because an import
    tucked inside a function is exactly how a dependency gets added without
    anybody noticing it in review.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:                       # a relative import, ours
                continue
            if node.module:
                roots.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
    return roots


@pytest.mark.parametrize("path", modules(), ids=lambda p: p.name)
def test_vibcore_does_not_import_either_service(path: Path):
    """One such import and the package belongs to one service again."""
    offending = imported_roots(path) & FORBIDDEN_ROOTS
    assert not offending, (
        f"vibcore/{path.name} imports {sorted(offending)}. vibcore is shared "
        f"by the platform and the chatbot, and neither can import the "
        f"other's modules -- so this either breaks one service outright or "
        f"quietly gives it the other's configuration. Move what is needed "
        f"into vibcore, or keep the code that needs it in the service."
    )


@pytest.mark.parametrize("path", modules(), ids=lambda p: p.name)
def test_vibcore_takes_on_no_new_dependencies(path: Path):
    """Both services pay for anything added here."""
    roots = imported_roots(path)
    unexpected = {
        r for r in roots
        if r not in ALLOWED_THIRD_PARTY
        and r not in STDLIB_HINT
        and r not in FORBIDDEN_ROOTS
        and r != "vibcore"
    }
    assert not unexpected, (
        f"vibcore/{path.name} imports {sorted(unexpected)}, which is neither "
        f"standard library nor on the allowed list. Both services inherit "
        f"it -- the chatbot's environment and the platform's Docker image. "
        f"If it is genuinely needed, add it to ALLOWED_THIRD_PARTY here and "
        f"to both services' requirements, deliberately."
    )


def test_the_reference_tables_travelled_with_the_code():
    """A module that reads a table it cannot find fails on first call, not
    at import -- so this is invisible until a user asks a question."""
    data = VIBCORE / "data"
    for name in ("bearings.json", "iso10816_3.json", "fault_signatures.json"):
        assert (data / name).is_file(), (
            f"{name} is missing from {data}. The modules resolve it relative "
            f"to their own location, so it has to move whenever they do."
        )


def test_the_package_declares_how_it_is_installed():
    """The chatbot installs this from the repo. Without the packaging
    metadata that install silently becomes 'not installed', and the chatbot
    falls back to whatever else answers to the name."""
    pyproject = VIBCORE / "pyproject.toml"
    assert pyproject.is_file(), f"{pyproject} is missing"
    text = pyproject.read_text(encoding="utf-8")
    assert 'name = "vibcore"' in text
    assert 'vibcore = "."' in text, (
        "package-dir must map vibcore onto this directory itself, or the "
        "backend's 'import vibcore' and the chatbot's installed copy stop "
        "being the same files"
    )
