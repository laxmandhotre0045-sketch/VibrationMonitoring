"""Filesystem locations, and the .env load that every other config module depends on.

BASE_DIR is computed as parents[2] of this file, so this module must stay at
exactly app/<package>/<module>.py. Moving it a level deeper or shallower
silently repoints data/, logs/, static/ and the machine store at a directory
that does not exist - and nothing raises: list_ready_doc_ids() just returns [].
"""

import os as _os
from pathlib import Path as _Path

BASE_DIR = _Path(__file__).resolve().parent.parent.parent

# Load .env from project root; override=True so .env wins over stale shell vars.
try:
    from dotenv import load_dotenv as _load_dotenv

    _load_dotenv(BASE_DIR / ".env", override=True)
except ImportError:
    pass

if not (BASE_DIR / "app").is_dir():  # pragma: no cover - misconfiguration guard
    # Fail loudly rather than silently reading an empty corpus. `raise`, not
    # `assert`: asserts are stripped under python -O.
    raise RuntimeError(
        f"BASE_DIR resolved to {BASE_DIR}, which has no app/ directory. "
        "app/config/paths.py must stay at app/<package>/<module>.py."
    )

DATA_DIR = BASE_DIR / "data"
DOCUMENTS_DIR = DATA_DIR / "documents"
LOGS_DIR = BASE_DIR / "logs"

# Measurement-side storage. Deliberately a sibling of DOCUMENTS_DIR, never a
# child: index_service.list_ready_doc_ids() and ingest_service.list_documents()
# treat every subdirectory of DOCUMENTS_DIR as a document, so anything stored
# there would surface as a failed document in the picker. Any future
# signals/charts/measurements directories must follow the same rule.
MACHINES_DIR = DATA_DIR / "machines"

GRAPH_CHECKPOINT_PATH = DATA_DIR / "graph_checkpoints.sqlite"
INTERACTION_LOG_PATH = LOGS_DIR / "interactions.jsonl"

SUPPORTED_EXTENSIONS = {".pdf", ".docx"}
