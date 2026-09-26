"""Shared fixtures.

The API tests talk to a real PostgreSQL. They are not run against SQLite, and
that is deliberate: this schema is Postgres all the way down — `JSONB`, `ARRAY`,
`gen_random_uuid()`, and the `ON CONFLICT` upserts behind `save_upload_data` and
the job queue. A SQLite stand-in would be a different database wearing the same
models, and it would have passed happily through the exact bugs those upserts
were written to fix.

So: no database reachable, no API tests. They skip with an explanation rather
than failing, and everything that does not need one — the architecture rules and
the pipeline unit tests — still runs.

Point them at a database with::

    TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5433/vibration_test

or let it derive one from `DATABASE_URL` by appending `_test` to the database
name. The schema is built by running the real migrations, so the tests exercise
the alembic chain as well as the code.
"""
from __future__ import annotations

import os
from typing import Iterator
from urllib.parse import urlsplit, urlunsplit

import pytest

def _resolve_test_database_url() -> str | None:
    """Where the API tests should write, worked out before any app import.

    `TEST_DATABASE_URL` wins; otherwise `DATABASE_URL` supplies a
    `<name>_test` sibling. Returns None when there is nothing to work from.
    """
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit

    base = os.environ.get("DATABASE_URL", "")
    if not base:
        return None
    parts = urlsplit(base)
    name = parts.path.lstrip("/")
    if not name or name.endswith("_test"):
        return base if name else None
    return urlunsplit(parts._replace(path=f"/{name}_test"))


# Point the whole application at the test database *before* importing any of
# it. `app.config.settings` is built at import time and `app.database.engine`
# with it, and alembic's env.py reuses that same settings object — so anything
# set afterwards is already too late, and the migrations would run against the
# development database while the tests ran against the test one.
TEST_DATABASE_URL = _resolve_test_database_url()
if TEST_DATABASE_URL:
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
else:
    # Nothing configured: give the import a value it can parse. Every fixture
    # that needs a database skips, so this URL is never dialled.
    os.environ["DATABASE_URL"] = "postgresql+psycopg://localhost/placeholder"
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

ADMIN_EMAIL = "test-admin@example.com"
ADMIN_PASSWORD = "TestAdmin@2024"
VIEWER_EMAIL = "test-viewer@example.com"
VIEWER_PASSWORD = "TestViewer@2024"


def _database_name(url: str) -> str:
    return urlsplit(url).path.lstrip("/")


@pytest.fixture(scope="session")
def database_url() -> str:
    url = TEST_DATABASE_URL
    if url is None:
        pytest.skip(
            "No test database configured. Set TEST_DATABASE_URL (or DATABASE_URL, "
            "from which a '<name>_test' database is derived), e.g. "
            "TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5433/vibration_test"
        )
    # These tests migrate and write. Pointing them at a development database by
    # leaving an environment variable set is a mistake worth making impossible
    # rather than merely unlikely.
    if not _database_name(url).endswith("_test"):
        pytest.fail(
            f"Refusing to run against {_database_name(url)!r}: these tests migrate and "
            "write, so the database name must end in '_test'."
        )
    return url


@pytest.fixture(scope="session")
def engine(database_url: str):
    eng = sa.create_engine(database_url, pool_pre_ping=True)
    try:
        with eng.connect() as connection:
            connection.execute(sa.text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — any connection problem means skip
        eng.dispose()
        pytest.skip(
            f"No database at {_database_name(database_url)!r} ({type(exc).__name__}). "
            "Start one with `docker compose up -d postgres`, create the database, "
            "and set TEST_DATABASE_URL."
        )

    _migrate(database_url)
    yield eng
    eng.dispose()


def _migrate(url: str) -> None:
    """Build the schema with the real migrations, not `create_all`.

    `create_all` would build the schema the models describe, which is not
    necessarily the schema the migrations produce — and the difference between
    those two is exactly the bug a migration test exists to find.
    """
    from alembic import command
    from alembic.config import Config

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config = Config(os.path.join(root, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(root, "alembic"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")


@pytest.fixture
def db(engine) -> Iterator[Session]:
    """A session whose writes are rolled back when the test ends.

    The endpoints under test commit. Joining the session to an outer
    transaction with `create_savepoint` turns those commits into savepoint
    releases, so the code runs exactly as it does in production while the test
    still leaves the database as it found it — no truncation, no ordering
    dependencies between tests.
    """
    connection = engine.connect()
    transaction = connection.begin()
    factory = sessionmaker(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    session = factory()
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture
def client(db: Session):
    """An HTTP client wired to the ASGI app, sharing the test's session.

    `TestClient` is httpx underneath — it drives a real `httpx.Client` through
    a transport that calls the ASGI app in-process. Used rather than
    `httpx.ASGITransport` directly because that transport is async-only, and
    async tests here would buy nothing but `await` on every line.

    Constructed without `with`, so lifespan never runs and the application's
    startup seeding never fires. That is wanted: these tests create the users
    they need with known credentials rather than depending on the environment.
    """
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    test_client = TestClient(app, base_url="http://testserver")
    try:
        yield test_client
    finally:
        test_client.close()
        app.dependency_overrides.clear()


def _create_user(db: Session, email: str, password: str, roles: list[str]):
    from app.crud import user as user_crud
    from app.services.auth_service import hash_password

    existing = user_crud.get_user_by_email(db, email)
    if existing:
        return existing
    return user_crud.create_user(
        db=db,
        email=email,
        password_hash=hash_password(password),
        full_name=f"Test {roles[0]}",
        role_names=roles,
        must_change_password=False,
    )


@pytest.fixture
def admin_user(db: Session):
    return _create_user(db, ADMIN_EMAIL, ADMIN_PASSWORD, ["super_admin"])


@pytest.fixture
def viewer_user(db: Session):
    return _create_user(db, VIEWER_EMAIL, VIEWER_PASSWORD, ["user"])


def login(client, email: str, password: str) -> dict:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def admin_tokens(client, admin_user) -> dict:
    return login(client, ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture
def admin_headers(admin_tokens) -> dict:
    return {"Authorization": f"Bearer {admin_tokens['access_token']}"}


@pytest.fixture
def viewer_headers(client, viewer_user) -> dict:
    tokens = login(client, VIEWER_EMAIL, VIEWER_PASSWORD)
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture
def sensor_id(db: Session):
    """A real sensor, because uploads carry a foreign key to one.

    Created through the same tables the application uses rather than by
    disabling the constraint: a fixture that switched the referential
    integrity off would let a test pass against a database state the
    application can never reach.
    """
    import uuid

    equipment = uuid.uuid4()
    sensor = uuid.uuid4()
    db.execute(sa.text("""
        INSERT INTO equipment_masters
            (id, plant_name, area, line, machine_name, machine_type,
             machine_criticality)
        VALUES (:id, 'Test Plant', 'Test Area', 'Test Line',
                'Test Pump', 'pump', 'medium')
    """), {"id": str(equipment)})
    db.execute(sa.text("""
        INSERT INTO sensor_configurations
            (id, equipment_id, sensor_type, mounting_location, orientation,
             sensitivity)
        VALUES (:id, :eq, 'accelerometer', 'drive end', 'radial', 100.0)
    """), {"id": str(sensor), "eq": str(equipment)})
    db.flush()
    return sensor
