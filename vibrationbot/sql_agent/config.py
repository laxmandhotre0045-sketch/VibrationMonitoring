"""Settings for the sensor SQL agent.

Deliberately standalone: this package must import cleanly without pulling in the
chatbot's retrieval stack, so another agent can depend on it without dragging
faiss and docling along. Nothing here imports from ``app``.

PLATFORM_PASSWORD has no default. An unset password fails the first call with a
clear message rather than silently attempting an anonymous request that returns
401 much later, somewhere less obvious.
"""

from __future__ import annotations

import os as _os
from pathlib import Path as _Path

#: vibrationbot/ - this file is sql_agent/config.py, so two parents up.
BASE_DIR = _Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv as _load_dotenv

    _load_dotenv(BASE_DIR / ".env", override=False)
except ImportError:  # pragma: no cover - dotenv is optional for library use
    pass


def _read() -> dict[str, object]:
    """Read settings from the environment at call time.

    Module constants are captured at import, which makes a library awkward to
    reconfigure from a host process that sets its own environment. The values
    below stay available as constants for convenience, but every entry point
    re-reads through this so a caller can override without reimporting.
    """
    return {
        "base_url": _os.getenv("PLATFORM_BASE_URL", "http://localhost:8000").rstrip("/"),
        "email": _os.getenv("PLATFORM_EMAIL", "user@vibration.com"),
        "password": _os.getenv("PLATFORM_PASSWORD", ""),
        "timeout_s": float(_os.getenv("PLATFORM_TIMEOUT_S", "30")),
        "max_captures": int(_os.getenv("PLATFORM_MAX_UPLOADS", "200")),
    }


PLATFORM_BASE_URL = _read()["base_url"]
PLATFORM_EMAIL = _read()["email"]
PLATFORM_PASSWORD = _read()["password"]
PLATFORM_TIMEOUT_S = _read()["timeout_s"]

#: Upper bound on captures pulled per request. A sensor capturing hourly
#: produces ~720 a month and each costs a features call, so this is a latency
#: guard as much as a memory one. Results report when they truncate rather than
#: implying the history is complete.
PLATFORM_MAX_UPLOADS = _read()["max_captures"]

#: Rows echoed into a preview for a calling agent. The full set is always in
#: ``rows``; this only bounds what a language model would read, so a large
#: export cannot flood a context window.
PLATFORM_CSV_PREVIEW_ROWS = int(_os.getenv("PLATFORM_CSV_PREVIEW_ROWS", "15"))

#: Where CSV files land when a caller asks for one on disk. Optional - the
#: agent returns CSV text regardless and only touches the filesystem on request.
EXPORTS_DIR = BASE_DIR / "data" / "exports"
