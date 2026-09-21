"""Shared pytest fixtures."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def _isolate_ingest_lock():
    """Redirect the ingest lock to a temp path for the whole test session.

    The real lock lives at data/.ingest.lock and serializes ingests across the
    project. Without this, running the suite while a real ingest is in progress
    would make the test fixtures' own ingests fail with IngestBusyError.

    The import is inside the fixture and tolerates failure. It used to sit at
    module level, where it pulled the whole ingestion pipeline -- pymupdf,
    langchain, faiss, sentence-transformers -- into every test session. One
    missing library therefore blocked collection of EVERY test in this
    directory, including pure-domain ones that touch none of it. A test that
    guards a JSON file should not be reachable only through a PDF library.

    When ingestion cannot be imported there is no ingest lock to protect, so
    there is nothing for this fixture to do.
    """
    try:
        from app.ingestion import ingest_service
    except ImportError:
        yield
        return

    tmp = Path(tempfile.mkdtemp(prefix="test_ingest_lock_"))
    ingest_service._LOCK_PATH = tmp / ".ingest.lock"
    yield
