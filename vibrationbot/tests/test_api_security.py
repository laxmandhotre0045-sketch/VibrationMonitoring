"""Path-traversal and doc_id validation tests for the documents API."""

import pytest
from fastapi.testclient import TestClient

from app.api.routes_documents import _safe_asset_path, _safe_doc_id
from app.main import app
from app.config import DOCUMENTS_DIR

from fastapi import HTTPException


@pytest.fixture(scope="module")
def client():
    # Skip lifespan (model preload) — these tests never touch retrieval.
    return TestClient(app)


@pytest.fixture(scope="module")
def secret_file():
    """A file outside DOCUMENTS_DIR that traversal would try to reach."""
    target = DOCUMENTS_DIR.parent / "traversal_canary.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("CANARY", encoding="utf-8")
    yield target
    target.unlink(missing_ok=True)


TRAVERSAL_FILENAMES = [
    "../../traversal_canary.txt",
    "..%2f..%2ftraversal_canary.txt",
    "....//....//traversal_canary.txt",
    "/etc/passwd",
    "C:\\Windows\\win.ini",
    "..\\..\\traversal_canary.txt",
]


@pytest.mark.parametrize("filename", TRAVERSAL_FILENAMES)
def test_asset_traversal_is_refused(client, secret_file, filename):
    resp = client.get(f"/api/v1/documents/somedoc/assets/{filename}")
    assert resp.status_code in (400, 404), resp.status_code
    assert "CANARY" not in resp.text


@pytest.mark.parametrize(
    "doc_id",
    ["../etc", "..", "a/b", "a\\b", "doc id", "", "x" * 200, "a.b", "%2e%2e"],
)
def test_invalid_doc_ids_are_rejected(doc_id):
    with pytest.raises(HTTPException) as exc:
        _safe_doc_id(doc_id)
    assert exc.value.status_code == 400


@pytest.mark.parametrize(
    "doc_id",
    ["cat2", "phase2_verify", "vdoc_pub_x_1_3", "Doc-123", "a"],
)
def test_valid_doc_ids_are_accepted(doc_id):
    assert _safe_doc_id(doc_id) == doc_id


def test_safe_asset_path_stays_inside_assets_dir():
    resolved = _safe_asset_path("mydoc", "figure_0001.png")
    expected_dir = (DOCUMENTS_DIR / "mydoc" / "assets").resolve()
    assert resolved.parent == expected_dir


def test_safe_asset_path_rejects_escape():
    with pytest.raises(HTTPException) as exc:
        _safe_asset_path("mydoc", "../../../secrets.txt")
    assert exc.value.status_code == 404


def test_traversal_via_doc_id_is_rejected(client, secret_file):
    resp = client.get("/api/v1/documents/..%2F..%2Fetc/assets/traversal_canary.txt")
    assert resp.status_code in (400, 404)
    assert "CANARY" not in resp.text


def test_upload_rejects_malicious_doc_id(client):
    resp = client.post(
        "/api/v1/documents/upload?doc_id=../../evil",
        files={"file": ("x.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert resp.status_code == 400
    assert not (DOCUMENTS_DIR.parent / "evil").exists()
