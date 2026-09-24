"""VIK-002 — the three reference data files load and answer a lookup.

The ticket describes a repository where `app/domain/data/` was absent because
`.gitignore` said `data/` rather than `/data/`, matching the folder at every
depth. The effect was that bearing geometry, the ISO tables and the fault rules
all raised on first call, which took out iso_agent entirely, the report agent's
bearing and ISO steps, and all five domain tools in the chat graph.

The files are present now. What this test protects is that they stay present
and stay loadable: a missing data file is invisible until something calls it,
and by then it is a traceback in front of a user rather than a red test.

These files moved with the code that reads them when VIK-035 extracted
`vibcore`. That also settled the complaint this test was written with: in the
chatbot these tests were reachable only through a package conftest that
imports the ingestion pipeline, so a missing bearing table could not be
caught without pymupdf installed. Here they need nothing but the package.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).resolve().parents[1] / "vibcore" / "data"
VIBCORE_DATA = DATA_DIR

EXPECTED_FILES = ("bearings.json", "iso10816_3.json", "fault_signatures.json")


# ------------------------------------------------------------ the files --

@pytest.mark.parametrize("name", EXPECTED_FILES)
def test_the_data_file_exists(name: str):
    path = DATA_DIR / name
    assert path.is_file(), (
        f"{name} is missing from {DATA_DIR}. Check that .gitignore says "
        f"'/data/' and not 'data/' -- the second form matches this folder too."
    )


@pytest.mark.parametrize("name", EXPECTED_FILES)
def test_the_data_file_is_valid_json_and_not_empty(name: str):
    """Present but truncated is a real failure mode for a file recovered by
    hand from another machine, and it looks identical to present-and-fine
    until something parses it."""
    payload = json.loads((DATA_DIR / name).read_text(encoding="utf-8"))
    assert payload, f"{name} parsed but is empty"


# ------------------------------------------------- one lookup in each --
#
# This is the ticket's stated acceptance test.

def test_bearing_lookup_answers():
    from vibcore import bearing

    geometry = bearing.resolve_bearing("6205")
    assert geometry is not None, "6205 is in the built-in catalogue and must resolve"
    assert geometry.n_balls > 0


def test_iso_lookup_answers():
    from vibcore import iso10816

    # Group 2, rigid foundation, a velocity inside the tables.
    result = iso10816.severity_zone(
        velocity_rms_mm_s=2.0, machine_group=2, foundation="rigid"
    )
    assert result.zone in {"A", "B", "C", "D"}


def test_fault_signature_lookup_answers():
    from vibcore import signatures

    # An empty peak list is a legitimate input and must return a list rather
    # than raise -- the point here is that the rules FILE loaded, which is
    # what the missing data folder broke.
    hypotheses = signatures.match_faults(peaks=[])
    assert isinstance(hypotheses, list)


# --------------------------------------------------- the original bug --

def test_no_gitignore_rule_excludes_the_reference_tables():
    """The single line that caused VIK-002, checked where the files now live.

    `data/` with no leading slash matches a folder called data at ANY depth.
    Written for a repository-root `data/`, it silently excluded the bundled
    reference tables too -- and a data file that is ignored is present on the
    machine that wrote it and absent everywhere else, which is the worst
    shape a bug can have.

    Every .gitignore above vibcore/data/ is checked, because any one of them
    can do it. The test moved from the chatbot to here with the files; the
    rule it guards travelled with them.
    """
    data_dir = VIBCORE_DATA
    checked = []
    for parent in list(data_dir.parents):
        candidate = parent / ".gitignore"
        if not candidate.is_file():
            continue
        checked.append(candidate)
        offending = [
            line for line in candidate.read_text(encoding="utf-8").splitlines()
            if line.strip() in ("data/", "data", "**/data/")
        ]
        assert not offending, (
            f"{candidate} contains {offending!r}, which matches a folder "
            f"called data at any depth -- including {data_dir}. Anchor it "
            f"with a leading slash, e.g. '/data/'."
        )
    assert checked, "no .gitignore found above the reference tables"
