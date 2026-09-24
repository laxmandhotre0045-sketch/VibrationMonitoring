"""The trust level that rides along with a set of features.

The engine that *decides* trust is VIK-022, and it is not in this repository
yet — no branch here defines a trust level, a check, or anything that produces
one. What this module holds is the half the API owes its callers regardless:
the one place the endpoint asks for an upload's verdict, and the coercion that
keeps whatever the engine returns inside the four levels the contract
publishes. Those four live with the contract, in `app.schemas.feature`.

Two rules shape everything below.

**Absent is not "High".** A missing verdict is reported as nothing at all, never
as a passing grade. Features computed before the engine existed, or while it was
switched off, are not trustworthy — they are unexamined, and an operator reading
a number off a screen deserves to be told which one they are looking at.

**The API emits only the four documented levels.** Whatever the engine hands
back — an enum, a string in some other case, a dataclass — it is normalized here
before it reaches a response, so the contract cannot drift with the
implementation.

When VIK-022 lands, `read_quality` is the only function that needs to change,
and possibly not even that: it already reads the verdict off the upload row, so
an engine that stores its result there is picked up as-is.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, cast

from app.schemas.feature import TRUST_LEVELS, TrustLevel

_BY_LOWERCASE: dict[str, TrustLevel] = {
    level.lower(): cast(TrustLevel, level) for level in TRUST_LEVELS
}


@dataclass(frozen=True)
class QualityVerdict:
    """One upload's data-quality result.

    `failed_checks` names the checks that did not pass, in the order the engine
    reported them. An empty list alongside a non-null level means everything
    passed — which is why "not assessed" is a missing verdict rather than an
    empty one.
    """

    trust_level: TrustLevel
    failed_checks: list[str] = field(default_factory=list)


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
    """Reduce a list of failed checks to the names the response carries.

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


def read_quality(upload: Any) -> Optional[QualityVerdict]:
    """The verdict for an upload, or None when nothing has assessed it.

    Reads the result off the upload row. Nothing writes those attributes today,
    so this returns None for every upload in this build — deliberately, per the
    first rule at the top of this module.

    It is written as an attribute read rather than a hard-coded None so that an
    engine storing its verdict on the upload needs no change here, and so the
    endpoint and its tests exercise the real path rather than a stub that will
    be deleted.
    """
    if upload is None:
        return None

    level = normalize_trust_level(
        getattr(upload, "trust_level", None) or getattr(upload, "data_trust_level", None)
    )
    if level is None:
        return None

    return QualityVerdict(
        trust_level=level,
        failed_checks=normalize_failed_checks(
            getattr(upload, "failed_checks", None)
            or getattr(upload, "data_quality_failed_checks", None)
        ),
    )
