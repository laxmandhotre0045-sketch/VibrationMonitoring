"""Terminal progress helpers for the ingestion pipeline."""

from __future__ import annotations

import logging
import sys
from datetime import datetime

logger = logging.getLogger(__name__)

# Best-effort: force UTF-8 on the console so Unicode in progress messages
# (e.g. the "→" arrow) never raises UnicodeEncodeError on Windows cp1252.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _emit(line: str, *, err: bool = False) -> None:
    """Print a line, falling back to ASCII if the console can't encode it."""
    stream = sys.stderr if err else sys.stdout
    try:
        print(line, file=stream, flush=True)
    except UnicodeEncodeError:
        enc = getattr(stream, "encoding", None) or "ascii"
        print(line.encode(enc, "replace").decode(enc), file=stream, flush=True)


def step(current: int, total: int, message: str, *, doc_id: str = "") -> None:
    prefix = f"[{current}/{total}]"
    doc = f" ({doc_id})" if doc_id else ""
    line = f"{_ts()} {prefix}{doc} {message}"
    _emit(line)
    logger.info(line)


def banner(message: str) -> None:
    line = f"\n{'=' * 60}\n{_ts()}  {message}\n{'=' * 60}"
    _emit(line)
    logger.info(message)


def success(message: str) -> None:
    line = f"{_ts()}  OK  {message}"
    _emit(line)
    logger.info(message)


def error(message: str) -> None:
    line = f"{_ts()}  FAIL  {message}"
    _emit(line, err=True)
    logger.error(message)


def summary(rows: list[tuple[str, str]]) -> None:
    _emit(f"\n{_ts()}  Summary:")
    for label, value in rows:
        _emit(f"    {label}: {value}")
