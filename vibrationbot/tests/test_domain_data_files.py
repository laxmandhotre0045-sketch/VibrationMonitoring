"""VIK-002 — the three reference data files load and answer a lookup.

The ticket describes a repository where `app/domain/data/` was absent because
`.gitignore` said `data/` rather than `/data/`, matching the folder at every
depth. The effect was that bearing geometry, the ISO tables and the fault rules
all raised on first call, which took out iso_agent entirely, the report agent's
bearing and ISO steps, and all five domain tools in the chat graph.

The files are present now. What this test protects is that they stay present
and stay loadable: a missing data file is invisible until something calls it,
and by then it is a traceback in front of a user rather than a red test.

Deliberately importing only `app.domain`. The existing domain tests cannot run
here at all -- the package conftest imports the ingestion pipeline, which needs
pymupdf, so collection fails before any domain test executes. A test that
guards a data file should not be reachable only through a PDF library.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).resolve().parents[1] / "app" / "domain" / "data"

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
    from app.domain import bearing

    geometry = bearing.resolve_bearing("6205")
    assert geometry is not None, "6205 is in the built-in catalogue and must resolve"
    assert geometry.n_balls > 0


def test_iso_lookup_answers():
    from app.domain import iso10816

    # Group 2, rigid foundation, a velocity inside the tables.
    result = iso10816.severity_zone(
        velocity_rms_mm_s=2.0, machine_group=2, foundation="rigid"
    )
    assert result.zone in {"A", "B", "C", "D"}


def test_fault_signature_lookup_answers():
    from app.domain import signatures

    # An empty peak list is a legitimate input and must return a list rather
    # than raise -- the point here is that the rules FILE loaded, which is
    # what the missing data folder broke.
    hypotheses = signatures.match_faults(peaks=[])
    assert isinstance(hypotheses, list)


# --------------------------------------------------- the original bug --

def test_gitignore_does_not_match_the_domain_data_folder():
    """The single line that caused this.

    `data/` with no leading slash matches a folder called data at ANY depth,
    so it silently excluded app/domain/data/ as well as the repository-root
    data/ it was written for.
    """
    gitignore = Path(__file__).resolve().parents[1] / ".gitignore"
    if not gitignore.is_file():
        pytest.skip("vibrationbot/.gitignore not present")

    offending = [
        line for line in gitignore.read_text(encoding="utf-8").splitlines()
        if line.strip() == "data/"
    ]
    assert not offending, (
        "vibrationbot/.gitignore contains a bare 'data/' rule, which matches "
        "app/domain/data/ as well as the root data/ folder. Use '/data/'."
    )
