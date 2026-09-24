"""Which module may depend on which.

Layering is the kind of rule that is obvious when written down and invisible in
a diff. These tests read the import graph straight from the source with `ast` —
no imports, no database, no application startup — so they run anywhere and cost
milliseconds.

**This would have caught the pipeline duplication (VIK-011).** Before that fix,
`routers/ingest.py` and `routers/measurements.py` each imported
`persist_all_plot_results` and `persist_upload_features_and_trends` directly and
called them in their own hand-written order. Two copies drifted, only one of
them counted raised alerts, and the divergence was invisible because nothing
said the routers were not allowed to reach past the pipeline.
`test_pipeline_internals_have_one_caller` is that rule.

**It also guards the pipeline's HTTP-freedom.** `measurement_pipeline`'s
docstring promises it "knows nothing about HTTP: no request, no api_key, no
status codes. That is deliberate, and it is the whole point of the file."
`test_only_the_http_layer_imports_fastapi` is what keeps that true — a promise
in a docstring is a comment, a promise in a test is a rule.

Adding a legitimate exception means adding it to the allow-list below, in a
commit where a reviewer can see it and ask why.
"""
from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parent.parent / "app"


def _module_name(path: Path) -> str:
    relative = path.relative_to(APP_DIR.parent).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _build_import_graph() -> dict[str, set[str]]:
    """module -> everything it imports, including imported names.

    Recording `app.crud.user.SUPPORTED_ROLES` as well as `app.crud.user` is what
    lets a rule talk about a specific function rather than only a module.
    """
    graph: dict[str, set[str]] = defaultdict(set)
    for path in sorted(APP_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        name = _module_name(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    graph[name].add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level or not node.module:
                    continue  # relative imports stay within their own package
                graph[name].add(node.module)
                for alias in node.names:
                    graph[name].add(f"{node.module}.{alias.name}")
    return graph


@pytest.fixture(scope="module")
def imports() -> dict[str, set[str]]:
    return _build_import_graph()


def _matches(imported: str, target: str) -> bool:
    return imported == target or imported.startswith(target + ".")


def _violations(
    imports: dict[str, set[str]],
    *,
    layer: str,
    forbidden: tuple[str, ...],
    allowed: frozenset[tuple[str, str]] = frozenset(),
) -> list[str]:
    found = []
    for module, imported_names in sorted(imports.items()):
        if not _matches(module, layer):
            continue
        for imported in sorted(imported_names):
            if not any(_matches(imported, bad) for bad in forbidden):
                continue
            # Allow-list entries name the module and the top-level package it
            # is allowed to reach, not every symbol inside it.
            root = ".".join(imported.split(".")[:3])
            if (module, root) in allowed:
                continue
            found.append(f"{module} -> {imported}")
    return found


# ---------------------------------------------------------------------------
# Known exceptions, grandfathered so new ones still fail
# ---------------------------------------------------------------------------

#: Each of these predates the rule. They are listed rather than ignored so the
#: rule can be switched on now and the list emptied later — a rule with three
#: exceptions still catches the fourth.
GRANDFATHERED: frozenset[tuple[str, str]] = frozenset(
    {
        # Reads RULE_TYPES / SUPPORTED_ROLES to build its validators, so the
        # accepted values are defined once. Worth inverting one day: the
        # constants belong lower than either layer.
        ("app.schemas.threshold", "app.services.threshold_defaults"),
        ("app.schemas.user", "app.crud.user"),
        # Imports SEVERITY_ORDER, a constant that lives on the model.
        ("app.schemas.integration", "app.models.integration"),
        # Reuses the threshold status constants when grading a machine.
        ("app.crud.dashboard", "app.services.threshold_evaluator"),
    }
)


# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------


def test_models_do_not_depend_on_anything_above_them(imports):
    """A model describes a row. It cannot know who reads it."""
    assert not _violations(
        imports,
        layer="app.models",
        forbidden=("app.crud", "app.services", "app.routers", "app.dependencies"),
    )


def test_crud_does_not_depend_on_routers(imports):
    """Queries cannot reach back up into the HTTP layer."""
    assert not _violations(
        imports, layer="app.crud", forbidden=("app.routers", "app.dependencies")
    )


def test_services_do_not_depend_on_routers(imports):
    """A service is callable from an endpoint, a worker or a script.

    The worker added in VIK-013 depends on this being true: it runs the
    measurement pipeline with no FastAPI anywhere in the process.
    """
    assert not _violations(
        imports, layer="app.services", forbidden=("app.routers", "app.dependencies")
    )


def test_schemas_stay_below_crud_and_services(imports):
    """Request and response shapes are data, not behaviour."""
    assert not _violations(
        imports,
        layer="app.schemas",
        forbidden=("app.crud", "app.services", "app.routers"),
        allowed=GRANDFATHERED,
    )


def test_crud_does_not_depend_on_services(imports):
    assert not _violations(
        imports, layer="app.crud", forbidden=("app.services",), allowed=GRANDFATHERED
    )


def test_only_the_http_layer_imports_fastapi(imports):
    """Everything below the routers must be callable without a request.

    This is the rule that keeps `measurement_pipeline` honest. The moment a
    service raises `HTTPException`, it stops being usable from the worker or a
    backfill script, and the failure only shows up wherever it is called next.
    """
    offenders = sorted(
        module
        for module, imported in imports.items()
        if any(_matches(name, "fastapi") or _matches(name, "starlette") for name in imported)
        and not (
            _matches(module, "app.routers")
            or _matches(module, "app.dependencies")
            or module == "app.main"
        )
    )
    assert not offenders


def test_pipeline_internals_have_one_caller(imports):
    """Plots and features are reached through the pipeline, not around it.

    This is the VIK-011 rule. Both upload paths used to import these directly
    and inline their own copy of the order to call them in; the copies drifted
    and one of them silently stopped counting alerts. Anything that needs this
    work asks `run_pipeline` for it, so a fix lands once.
    """
    internals = (
        "app.services.plot_storage.persist_all_plot_results",
        "app.services.feature_storage.persist_upload_features_and_trends",
    )
    callers = {
        internal: sorted(m for m, names in imports.items() if internal in names)
        for internal in internals
    }
    assert callers == {
        internal: ["app.services.measurement_pipeline"] for internal in internals
    }


def test_the_worker_is_an_entry_point_not_a_library(imports):
    """Nothing imports the worker.

    It is a process, like `app.main`. If application code starts importing it,
    the polling loop has leaked into the request path.
    """
    importers = sorted(
        module
        for module, imported in imports.items()
        if any(_matches(name, "app.worker") for name in imported)
    )
    assert not importers


def test_every_layer_is_actually_populated(imports):
    """Guards the guard.

    Every rule above is written as "no module in X imports Y". A typo in a
    layer name makes all of them pass by matching nothing, and the suite would
    stay green while enforcing nothing at all.
    """
    for layer in ("app.models", "app.schemas", "app.crud", "app.services", "app.routers"):
        assert any(_matches(m, layer) for m in imports), f"no modules found under {layer}"
