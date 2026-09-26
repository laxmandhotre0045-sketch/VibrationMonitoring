"""The trust level that rides along with a set of features.

The engine that *decides* trust is VIK-022, in `app.ai.quality`; it stores its
verdict through `app.services.quality_storage`, one row per channel plus one
for the capture as a whole. What this module holds is the half the API owes its
callers: the one place the endpoint asks for an upload's verdict, and the
coercion that keeps whatever the engine returns inside the four levels the
contract publishes. Those four live with the contract, in `app.schemas.feature`.

Three rules shape everything below.

**Absent is not "High".** A missing verdict is reported as nothing at all, never
as a passing grade. Features computed before the engine existed, or while it was
switched off, are not trustworthy — they are unexamined, and an operator reading
a number off a screen deserves to be told which one they are looking at.

**A check that could not run is not a check that passed.** The engine keeps that
third outcome and so does this module: `not_assessed` travels beside
`failed_checks` rather than being folded into it or dropped. Folding it into the
failures would invent problems; dropping it would report "clipping: fine" for a
record too short to judge clipping.

**The API emits only the four documented levels.** Whatever the engine hands
back — an enum, a string in some other case, a dataclass — it is normalized here
before it reaches a response, so the contract cannot drift with the
implementation. The engine's own vocabulary is lowercase, and its "unknown"
(what it returns when the assessment itself failed) is deliberately not one of
the four: it normalizes to None, which is the same as unassessed, because it is.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, cast
from uuid import UUID

from sqlalchemy.orm import Session

from app.schemas.feature import TRUST_LEVELS, TrustLevel

logger = logging.getLogger(__name__)

_BY_LOWERCASE: dict[str, TrustLevel] = {
    level.lower(): cast(TrustLevel, level) for level in TRUST_LEVELS
}


@dataclass(frozen=True)
class QualityVerdict:
    """One upload's data-quality result, for one channel or for the capture.

    `failed_checks` names the checks that ran and did not pass; `not_assessed`
    names the ones that could not run at all. Both empty alongside a non-null
    level means everything was checked and everything passed — which is why
    "not assessed" is a missing verdict rather than an empty one.
    """

    trust_level: TrustLevel
    failed_checks: list[str] = field(default_factory=list)
    not_assessed: list[str] = field(default_factory=list)


def normalize_trust_level(value: Any) -> Optional[TrustLevel]:
    """Coerce whatever the engine calls a trust level into one of the four.

    Accepts the strings themselves in any case, and anything enum-like by
    reading its `.value` or `.name`. Anything unrecognised is None: a level the
    API does not document is worse than no level, because a caller would have
    to guess where it sits in the ordering.
    """
    if value is None:
        return None

    for candidate in (value, getattr(value, "value", None), getattr(value, "name", None)):
        if isinstance(candidate, str):
            match = _BY_LOWERCASE.get(candidate.strip().lower())
            if match is not None:
                return match
    return None


def normalize_failed_checks(value: Any) -> list[str]:
    """Reduce a list of checks to the names the response carries.

    The engine may report checks as plain names or as records with a code and a
    message attached. Both flatten to a name here; blanks and duplicates are
    dropped, because a check listed twice reads as two separate problems.
    """
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return []

    try:
        entries = list(value)
    except TypeError:
        return []

    names: list[str] = []
    for entry in entries:
        name: Any = entry
        if isinstance(entry, dict):
            name = entry.get("code") or entry.get("check") or entry.get("name") or entry.get("id")
        elif not isinstance(entry, str):
            name = (
                getattr(entry, "code", None)
                or getattr(entry, "check", None)
                or getattr(entry, "name", None)
            )

        if isinstance(name, str) and name.strip() and name not in names:
            names.append(name.strip())

    return names


def verdict_from_assessments(
    assessments: Mapping[Any, Any],
    channel: Optional[int] = None,
) -> Optional[QualityVerdict]:
    """Pick the assessment that answers the question that was asked.

    `assessments` is what `quality_storage.latest_for_upload` returns: stored
    rows keyed by channel index, with the key None holding the capture-level
    verdict (the worst of its channels).

    Asking about the whole capture gets the capture-level row. Asking about one
    channel gets *that channel's* row and nothing else — no falling back to the
    capture. The capture's level is the worst of eight channels, so handing it
    back for channel 3 would report another channel's problem as channel 3's.
    A channel with no stored row was never assessed, and says so by returning
    None, per the first rule at the top of this module.
    """
    if not assessments:
        return None

    row = assessments.get(int(channel) if channel is not None else None)
    if row is None:
        return None

    level = normalize_trust_level(_field(row, "level"))
    if level is None:
        return None

    return QualityVerdict(
        trust_level=level,
        failed_checks=normalize_failed_checks(_field(row, "failed_checks")),
        not_assessed=normalize_failed_checks(_field(row, "not_assessed")),
    )


def _field(row: Any, name: str) -> Any:
    """Read a column off a mapping row or an object row, whichever arrived."""
    if isinstance(row, Mapping):
        return row.get(name)
    return getattr(row, name, None)


def read_quality(
    db: Session,
    upload_id: UUID,
    channel: Optional[int] = None,
) -> Optional[QualityVerdict]:
    """The stored verdict for an upload, or None when nothing assessed it.

    Never raises. The verdict is an annotation on the features, not the
    features themselves, and an upload whose quality could not be looked up is
    still an upload worth returning — losing the whole response to the thing
    that grades it would be the worst outcome available. A lookup that fails is
    logged and reported as unassessed, which is what it is.
    """
    # Imported here rather than at module scope: quality_storage pulls in numpy
    # and the engine, and the schema-facing helpers above are imported by code
    # that has no need of either.
    from app.services import quality_storage

    try:
        assessments = quality_storage.latest_for_upload(db, upload_id)
    except Exception:
        logger.exception("Could not read quality assessment for upload %s", upload_id)
        return None

    return verdict_from_assessments(assessments, channel)
