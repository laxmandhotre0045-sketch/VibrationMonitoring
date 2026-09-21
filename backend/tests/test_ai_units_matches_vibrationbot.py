"""The ported units module must stay identical to the one it was copied from.

VIK-004 says to copy vibrationbot/app/domain/units.py into the backend rather
than rewrite it, because the conversions are tested against published values
and a second implementation would drift. Copying solves today's problem and
creates tomorrow's: two files, one of which gets edited.

The roadmap is explicit about what that costs -- it wants a shared package
precisely to stop "the two services drifting into two different answers for
the same bearing". VIK-035 does that properly. Until it lands, this test is
what makes the duplication safe: it compares the two files directly, so a
change to either one fails here on the same day it is made rather than
surfacing months later as two systems disagreeing about a severity.

Skipped rather than failed when vibrationbot is not present, so the backend
can be tested on its own -- but it will run in any checkout that has both,
which is every developer machine and CI.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

BACKEND_UNITS = Path(__file__).resolve().parents[1] / "app" / "ai" / "units.py"
BACKEND_RECORDS = Path(__file__).resolve().parents[1] / "app" / "ai" / "records.py"
VIBBOT = Path(__file__).resolve().parents[2] / "vibrationbot" / "app" / "domain"

#: The only differences the port is allowed to introduce.
ALLOWED_EDITS = (
    # the import was re-pointed at the sibling module
    ("from app.domain.records import", "from app.ai.records import"),
)


def _normalise(text: str) -> str:
    """Strip the things the port is allowed to change.

    The header note explaining that this is a copy is expected to differ, and
    so is the import line. Everything else -- every constant, every formula,
    every guard -- must match character for character.
    """
    for original, ported in ALLOWED_EDITS:
        text = text.replace(ported, original)

    # Drop the PORTED FROM note added to the backend copy's docstring.
    text = re.sub(
        r"\n\nPORTED FROM vibrationbot.*?rather than the day someone notices "
        r"two different answers\.\n",
        "", text, flags=re.DOTALL,
    )
    # Trailing whitespace and line endings differ between checkouts on Windows.
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


@pytest.mark.skipif(not VIBBOT.is_dir(), reason="vibrationbot not in this checkout")
def test_units_is_an_unmodified_copy():
    ported = _normalise(BACKEND_UNITS.read_text(encoding="utf-8"))
    source = _normalise((VIBBOT / "units.py").read_text(encoding="utf-8"))
    assert ported == source, (
        "backend/app/ai/units.py has diverged from "
        "vibrationbot/app/domain/units.py. Until VIK-035 extracts the shared "
        "package, a change must be made in both or in neither -- otherwise the "
        "two services will report different numbers for the same reading."
    )


@pytest.mark.skipif(not VIBBOT.is_dir(), reason="vibrationbot not in this checkout")
def test_records_is_an_unmodified_copy():
    ported = _normalise(BACKEND_RECORDS.read_text(encoding="utf-8"))
    source = _normalise((VIBBOT / "records.py").read_text(encoding="utf-8"))
    assert ported == source, (
        "backend/app/ai/records.py has diverged from "
        "vibrationbot/app/domain/records.py."
    )


def test_the_broadband_warning_survived_the_port():
    """The module's own caveat, which VIK-004 says explicitly to keep.

    Velocity from acceleration is exact only at a single frequency. Applied to
    a broadband overall reading it treats all the energy as if it sat at one
    frequency, which it does not -- and the resulting number looks entirely
    ordinary. Losing this warning in a copy-paste is a realistic way for the
    caveat to disappear while the maths stays right.
    """
    text = BACKEND_UNITS.read_text(encoding="utf-8").lower()
    assert "broadband" in text
    assert "frequency domain" in text
