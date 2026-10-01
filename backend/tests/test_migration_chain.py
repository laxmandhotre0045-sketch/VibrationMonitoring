"""A migration must land at the end of the chain, and stay where it landed.

Alembic records only where a database is now, never the path it took. So a
migration slotted in *behind* an existing one runs on a database built from
scratch and never on a database already past it: `upgrade head` from 028
computes 028 -> 029 and does not walk backwards to collect a revision
someone inserted at 021. The table is never created, alembic still reports
head, and the first symptom is the code that needs it failing.

That is what happened here. `processing_jobs` was added as revision 021,
ahead of the migration already holding that number, which was renamed 021a
to make room. The development database, at 028, upgraded to 029, reported
head, and did not have the table -- the worker died with `relation
"processing_jobs" does not exist`. It was moved to 030.

**No test of the current chain can catch this**, and it is worth being
precise about why, because the obvious test looks like it should. Migrating
a second database to an older revision and then to head does not reproduce
it: under the *new* chain, reaching 028 necessarily passes through anything
inserted before 028. The chain is internally valid. What is wrong is its
relationship to databases that already exist -- and the current files hold
no record of that.

`alembic/released_revisions.txt` is that record, and these tests are what
make it mean something. The rest of the file covers properties the chain
must have on its own.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import create_engine, text

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSIONS = os.path.join(BACKEND, "alembic", "versions")
MANIFEST = os.path.join(BACKEND, "alembic", "released_revisions.txt")

#: A revision inside the chain's history, used to stand in for "a database
#: that has been in use for a while".
OLDER_REVISION = "028"

_REVISION = re.compile(r"^revision(?::\s*str)?\s*=\s*[\"']([^\"']+)[\"']", re.M)
_DOWN = re.compile(
    r"^down_revision(?::\s*[^=]+)?\s*=\s*(?:[\"']([^\"']+)[\"']|None)", re.M)


def migrations() -> dict[str, tuple[str, str]]:
    """revision -> (down_revision, filename) for every migration on disk."""
    found: dict[str, tuple[str, str]] = {}
    for name in sorted(os.listdir(VERSIONS)):
        if not name.endswith(".py") or name.startswith("__"):
            continue
        source = open(os.path.join(VERSIONS, name), encoding="utf-8").read()
        revision = _REVISION.search(source)
        if not revision:
            continue
        down = _DOWN.search(source)
        found[revision.group(1)] = (
            down.group(1) if down and down.group(1) else "None", name)
    assert found, f"no migrations found in {VERSIONS}"
    return found


def released() -> list[tuple[str, str]]:
    """(revision, down_revision) in release order, from the manifest."""
    entries = []
    with open(MANIFEST, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            assert len(parts) == 2, f"malformed manifest line: {line!r}"
            entries.append((parts[0], parts[1]))
    assert entries, f"{MANIFEST} lists no revisions"
    return entries


# ------------------------------------------------- the history guard ----

def test_released_revisions_keep_their_identity():
    """A revision databases have already run must not be renumbered or
    re-parented. Changing it rewrites history that has already happened
    somewhere, and nothing in the database will disagree out loud."""
    on_disk = migrations()
    for revision, down in released():
        assert revision in on_disk, (
            f"revision {revision} is in the released manifest but no longer "
            f"exists on disk. Databases are sitting at it; deleting or "
            f"renumbering it leaves them unable to find where they are."
        )
        actual_down, filename = on_disk[revision]
        assert actual_down == down, (
            f"{filename}: revision {revision} was released with parent "
            f"{down!r} and now claims {actual_down!r}. Re-parenting a "
            f"released migration changes what every database that already "
            f"ran it should have. If a new migration needs to go between "
            f"them, it does not -- it goes at the end."
        )


def test_a_new_migration_goes_at_the_end():
    """The rule the processing_jobs bug broke.

    A migration not yet in the manifest is new. It must hang off the last
    released revision, or off another new one that does -- never off
    something in the middle, which no existing database will ever revisit.
    """
    on_disk = migrations()
    entries = released()
    released_ids = {revision for revision, _ in entries}
    head = entries[-1][0]

    new = {r: d for r, (d, _) in on_disk.items() if r not in released_ids}
    if not new:
        return

    allowed = {head}
    remaining = dict(new)
    while remaining:
        landed = [r for r, d in remaining.items() if d in allowed]
        assert landed, (
            f"new migration(s) {sorted(remaining)} do not extend the chain. "
            f"Each hangs off {sorted({remaining[r] for r in remaining})}, "
            f"but the last released revision is {head!r}. A migration "
            f"inserted behind an existing one never runs on a database that "
            f"is already past it -- alembic does not walk backwards -- so it "
            f"works when built from scratch and silently does nothing "
            f"everywhere else. Move it to the end, and append it to "
            f"{os.path.basename(MANIFEST)}."
        )
        for revision in landed:
            allowed.add(revision)
            remaining.pop(revision)


def test_every_migration_on_disk_is_reachable():
    """A file nobody's down_revision points at is dead weight that looks
    live: it will be read in review and never run."""
    on_disk = migrations()
    parents = {down for down, _ in on_disk.values()}
    unreferenced = [
        f"{r} ({on_disk[r][1]})" for r in on_disk
        if r not in parents and r != _head_of(on_disk)
    ]
    assert not unreferenced, (
        f"these revisions are not the head and nothing follows them: "
        f"{sorted(unreferenced)}. They are orphaned."
    )


def _head_of(on_disk: dict[str, tuple[str, str]]) -> str:
    parents = {down for down, _ in on_disk.values()}
    heads = [r for r in on_disk if r not in parents]
    assert len(heads) == 1, f"expected one head, found {sorted(heads)}"
    return heads[0]


def test_the_chain_is_linear_and_single_headed():
    """Two heads mean two people numbered from the same parent, and which
    branch a database gets depends on the order alembic walks them."""
    on_disk = migrations()
    _head_of(on_disk)

    seen: dict[str, list[str]] = {}
    for revision, (down, name) in on_disk.items():
        seen.setdefault(down, []).append(f"{revision} ({name})")
    forks = {d: rs for d, rs in seen.items() if len(rs) > 1}
    assert not forks, (
        f"more than one migration claims the same parent: {forks}. The chain "
        f"has branched and the two sides have to be joined."
    )


# ------------------------------------------- what the schema must do ----

@pytest.fixture()
def throwaway_databases(database_url):
    """Two empty databases on the same server, dropped afterwards.

    Deliberately does not depend on the `engine` fixture: that migrates the
    shared test database, so a broken chain would take these tests down
    before they could report on it. The shared test database is untouched.
    """
    base = database_url.rsplit("/", 1)[0]
    admin = create_engine(base + "/postgres", isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        admin.dispose()
        pytest.skip(f"no PostgreSQL reachable ({type(exc).__name__})")

    names = [f"vibchain_{uuid.uuid4().hex[:10]}" for _ in range(2)]
    try:
        with admin.connect() as conn:
            for name in names:
                conn.execute(text(f'CREATE DATABASE "{name}"'))
        yield [base + "/" + name for name in names]
    finally:
        with admin.connect() as conn:
            for name in names:
                conn.execute(text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :n AND pid <> pg_backend_pid()"),
                    {"n": name})
                conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        admin.dispose()


def alembic(url: str, target: str):
    return subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", target],
        cwd=BACKEND, capture_output=True, text=True,
        env={**os.environ, "DATABASE_URL": url})


def schema_of(url: str) -> dict[str, set[str]]:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT table_name, column_name
                  FROM information_schema.columns
                 WHERE table_schema = 'public'
                   AND table_name <> 'alembic_version'
            """)).fetchall()
    finally:
        engine.dispose()
    schema: dict[str, set[str]] = {}
    for table, column in rows:
        schema.setdefault(table, set()).add(column)
    return schema


def test_the_whole_chain_applies_to_an_empty_database(throwaway_databases):
    """Head is reachable from nothing. Cheap, and it fails loudly the day a
    migration references something an earlier one did not create."""
    url = throwaway_databases[0]
    result = alembic(url, "head")
    assert result.returncode == 0, result.stderr[-2500:]
    assert "processing_jobs" in schema_of(url), (
        "the worker's queue table is missing from a fresh build of the chain"
    )


def test_stopping_part_way_reaches_the_same_schema(throwaway_databases):
    """The schema at head must not depend on when a database was created.

    This does not catch a migration inserted behind an existing one -- see
    the module docstring -- but it does catch one that behaves differently
    depending on what is already there, which is the other way two databases
    drift apart.
    """
    direct_url, staged_url = throwaway_databases

    assert alembic(direct_url, "head").returncode == 0
    assert alembic(staged_url, OLDER_REVISION).returncode == 0
    result = alembic(staged_url, "head")
    assert result.returncode == 0, result.stderr[-2500:]

    direct, staged = schema_of(direct_url), schema_of(staged_url)
    assert set(direct) == set(staged), (
        f"only when built directly: {sorted(set(direct) - set(staged))}; "
        f"only when staged through {OLDER_REVISION}: "
        f"{sorted(set(staged) - set(direct))}"
    )
    for table in sorted(direct):
        assert direct[table] == staged[table], (
            f"table {table} differs by route to head: "
            f"only-direct={sorted(direct[table] - staged[table])}, "
            f"only-staged={sorted(staged[table] - direct[table])}"
        )


def test_upgrading_twice_changes_nothing(throwaway_databases):
    """The deployment runs `alembic upgrade head` on every start, so head has
    to be a fixed point."""
    url = throwaway_databases[0]
    assert alembic(url, "head").returncode == 0
    before = schema_of(url)
    result = alembic(url, "head")
    assert result.returncode == 0, result.stderr[-2500:]
    assert schema_of(url) == before
