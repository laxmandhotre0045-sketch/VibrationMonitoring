"""Shared pytest fixtures."""

import tempfile
from pathlib import Path

import pytest

from app.ingestion import ingest_service


@pytest.fixture(scope="session", autouse=True)
def _isolate_ingest_lock():
    """Redirect the ingest lock to a temp path for the whole test session.

    The real lock lives at data/.ingest.lock and serializes ingests across the
    project. Without this, running the suite while a real ingest is in progress
    would make the test fixtures' own ingests fail with IngestBusyError.
    """
    tmp = Path(tempfile.mkdtemp(prefix="test_ingest_lock_"))
    ingest_service._LOCK_PATH = tmp / ".ingest.lock"
    yield
