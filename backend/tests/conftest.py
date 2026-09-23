"""A throwaway database for the tests that cannot honestly be faked.

Most of this suite works on fakes, and should: the analysis code is
arithmetic and a fake session proves more than a database round trip would.
The baseline lifecycle is the opposite case. Almost all of it IS the
database -- a partial unique index that permits one version in force, check
constraints that refuse a frozen version with no frozen_at, an insert that
supersedes the row it is replacing. A fake session would agree with whatever
the code did and prove nothing about any of that.

So these tests run against a real PostgreSQL, in a database created for the
run and dropped after it. The developer's own database is never touched, and
the schema is built by the real migrations rather than by a second copy of
the DDL that would drift from them.

Where no PostgreSQL is reachable the fixture skips with a reason, rather
than falling back to SQLite and quietly testing something else.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _maintenance_url(url: str) -> str:
    """The same server, but the database that always exists.

    CREATE DATABASE cannot run from inside the database being created, and
    cannot run inside a transaction at all.
    """
    return url.rsplit("/", 1)[0] + "/postgres"


@pytest.fixture(scope="session")
def pg_database():
    """Create a database for this run, migrate it, and drop it afterwards."""
    try:
        from app.config import settings
        base_url = settings.database_url
    except Exception as exc:                                  # pragma: no cover
        pytest.skip(f"no database configuration available: {exc}")

    name = f"vibtest_{uuid.uuid4().hex[:12]}"
    test_url = base_url.rsplit("/", 1)[0] + "/" + name

    admin = create_engine(_maintenance_url(base_url),
                          isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    except Exception as exc:
        admin.dispose()
        pytest.skip(f"no PostgreSQL available for lifecycle tests: {exc}")

    try:
        # A subprocess, because alembic's env.py reads the URL from the
        # application settings at import time. Handing it an environment is
        # the only way to point it somewhere else without mutating the
        # settings this process is already using.
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND, capture_output=True, text=True,
            env={**os.environ, "DATABASE_URL": test_url},
        )
        if result.returncode != 0:
            pytest.skip("could not migrate the test database:\n"
                        + result.stderr[-2000:])
        yield test_url
    finally:
        # Dispose before dropping: a pooled connection still open holds the
        # database and turns the drop into a hang.
        for engine in engine_cache.values():
            engine.dispose()
        engine_cache.clear()
        with admin.connect() as conn:
            # Anything still connected would block the drop. Nothing should
            # be, but a failed test can leave a session open and a leaked
            # database is worse than a rude disconnect.
            conn.execute(text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :n AND pid <> pg_backend_pid()"), {"n": name})
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        admin.dispose()


engine_cache: dict[str, object] = {}


@pytest.fixture()
def db(pg_database):
    """A session on the throwaway database, rolled back after each test.

    Rolled back rather than truncated: a test that leaves rows behind would
    change what the next one sees, and the order tests run in is not
    something any of them should depend on.
    """
    engine = engine_cache.get(pg_database)
    if engine is None:
        engine = create_engine(pg_database, pool_pre_ping=True)
        engine_cache[pg_database] = engine

    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, autocommit=False,
                           autoflush=False)()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def sensor_id(db):
    """A real sensor, because uploads carry a foreign key to one.

    Created through the same tables the application uses rather than by
    disabling the constraint: a fixture that switched the referential
    integrity off would let a test pass against a database state the
    application can never reach.
    """
    equipment = uuid.uuid4()
    sensor = uuid.uuid4()
    db.execute(text("""
        INSERT INTO equipment_masters
            (id, plant_name, area, line, machine_name, machine_type,
             machine_criticality)
        VALUES (:id, 'Test Plant', 'Test Area', 'Test Line',
                'Test Pump', 'pump', 'medium')
    """), {"id": str(equipment)})
    db.execute(text("""
        INSERT INTO sensor_configurations
            (id, equipment_id, sensor_type, mounting_location, orientation,
             sensitivity)
        VALUES (:id, :eq, 'accelerometer', 'drive end', 'radial', 100.0)
    """), {"id": str(sensor), "eq": str(equipment)})
    db.flush()
    return sensor
