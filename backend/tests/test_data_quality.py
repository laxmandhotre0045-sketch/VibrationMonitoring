"""The trust level on the features response.

The engine that decides trust is VIK-022, in `app.ai.quality`, and it stores its
verdict as rows — one per channel, plus one for the capture as a whole. These
tests cover the half the API owes its callers: that the response carries the
fields, that an unassessed measurement is reported as unassessed rather than as
passing, that the right row is picked for the channel that was asked about, and
that whatever shape the engine returns is narrowed to the four documented levels
before it reaches a caller.

The rows here are shaped as `quality_storage.latest_for_upload` returns them,
with the engine's own lowercase levels, so the normalization is exercised
against what the engine actually emits rather than against the contract's
casing.
"""
from __future__ import annotations

from enum import Enum

import pytest

from app.schemas.feature import TRUST_LEVELS, UploadFeaturesOut
from app.services.data_quality import (
    QualityVerdict,
    normalize_failed_checks,
    normalize_trust_level,
    read_quality,
    verdict_from_assessments,
)


def stored(level, failed=None, not_assessed=None, channel=None):
    """One row as the assessments table hands it back."""
    return {
        "channel": channel,
        "level": level,
        "confidence_factor": 1.0,
        "failed_checks": failed if failed is not None else [],
        "not_assessed": not_assessed if not_assessed is not None else [],
        "checks": [],
        "engine_version": "1",
        "assessed_at": None,
    }


# ---------------------------------------------------------------------------
# The contract
# ---------------------------------------------------------------------------


def test_the_response_carries_the_quality_fields():
    fields = UploadFeaturesOut.model_fields
    assert "trust_level" in fields
    assert "failed_checks" in fields
    assert "not_assessed_checks" in fields


def test_the_response_publishes_the_four_levels():
    # The frontend switches on these. A fifth level appearing without a schema
    # change is a value no screen knows how to place.
    schema = UploadFeaturesOut.model_json_schema()
    rendered = str(schema)
    for level in ("High", "Medium", "Low", "Invalid"):
        assert level in rendered, f"{level} is missing from the published schema"
    assert TRUST_LEVELS == ("High", "Medium", "Low", "Invalid")


def test_the_published_endpoint_advertises_the_quality_fields():
    """The done-criterion, checked where a caller would look.

    Asserting on the model alone would still pass if the endpoint were wired to
    a different response type, so this reads the generated OpenAPI for the path
    itself — which is also what the frontend generates its client from.
    """
    from app.main import app

    spec = app.openapi()
    path = "/api/v1/measurements/uploads/{upload_id}/features"
    assert path in spec["paths"]

    ref = spec["paths"][path]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]["$ref"]
    properties = spec["components"]["schemas"][ref.split("/")[-1]]["properties"]

    assert "trust_level" in properties
    assert properties["failed_checks"]["items"]["type"] == "string"
    assert properties["not_assessed_checks"]["items"]["type"] == "string"

    # The enum is the part a client can switch on exhaustively.
    levels = next(
        option["enum"] for option in properties["trust_level"]["anyOf"] if "enum" in option
    )
    assert levels == list(TRUST_LEVELS)


def test_an_unassessed_measurement_defaults_to_no_verdict():
    """Absent is not "High".

    The fields are optional so that every existing caller keeps working, which
    means the default is what an unassessed upload reports. It has to be the
    honest one: features nothing has checked are unexamined, not trustworthy.
    """
    defaults = UploadFeaturesOut.model_fields
    assert defaults["trust_level"].default is None
    assert defaults["failed_checks"].default_factory() == []
    assert defaults["not_assessed_checks"].default_factory() == []


# ---------------------------------------------------------------------------
# Picking the row that answers the question that was asked
# ---------------------------------------------------------------------------


def test_nothing_stored_reads_as_unassessed():
    # Every upload ingested before the engine landed.
    assert verdict_from_assessments({}) is None
    assert verdict_from_assessments({}, channel=0) is None


def test_the_capture_verdict_is_the_one_with_no_channel():
    assessments = {
        None: stored("low", ["clipping"]),
        0: stored("high", channel=0),
        3: stored("low", ["clipping"], channel=3),
    }

    verdict = verdict_from_assessments(assessments)

    assert verdict is not None
    assert verdict.trust_level == "Low"
    assert verdict.failed_checks == ["clipping"]


def test_a_channel_gets_its_own_verdict_not_the_whole_captures():
    """The distinction the channel scoping exists for.

    The capture's level is the worst of its channels. Channel 0 passed every
    check; reporting the capture's "low" against it would show channel 3's
    clipping as channel 0's problem.
    """
    assessments = {
        None: stored("low", ["clipping"]),
        0: stored("high", channel=0),
        3: stored("low", ["clipping"], channel=3),
    }

    channel_zero = verdict_from_assessments(assessments, channel=0)
    assert channel_zero.trust_level == "High"
    assert channel_zero.failed_checks == []

    channel_three = verdict_from_assessments(assessments, channel=3)
    assert channel_three.trust_level == "Low"
    assert channel_three.failed_checks == ["clipping"]


def test_a_channel_with_no_row_does_not_borrow_the_captures_verdict():
    # Falling back would attribute a grade to a channel nothing graded, which
    # is the same mistake as reporting "High" for an unassessed upload.
    assessments = {None: stored("invalid", ["flatline"]), 0: stored("high", channel=0)}

    assert verdict_from_assessments(assessments, channel=7) is None


def test_the_engines_lowercase_levels_reach_the_contracts_casing():
    """The engine emits "high"; the API publishes "High".

    Worth its own test because the failure is silent: a level that did not
    normalize would be reported as no level at all, and the response would look
    exactly like an unassessed upload.
    """
    for engine_level, published in [
        ("high", "High"),
        ("medium", "Medium"),
        ("low", "Low"),
        ("invalid", "Invalid"),
    ]:
        verdict = verdict_from_assessments({None: stored(engine_level)})
        assert verdict is not None, f"{engine_level} normalized to nothing"
        assert verdict.trust_level == published


def test_an_assessment_that_could_not_run_reads_as_unassessed():
    # The engine reports "unknown" when the assessment itself failed. It is not
    # one of the four, and it means the same as no verdict.
    assert verdict_from_assessments({None: stored("unknown")}) is None


def test_checks_that_could_not_run_are_kept_apart_from_failures():
    """A check that could not be run is not a check that passed.

    Folding these into failed_checks would invent problems; dropping them would
    report "speed steady" for a record too short to judge steadiness.
    """
    verdict = verdict_from_assessments(
        {None: stored("medium", ["clipping"], ["speed_steady", "bearing_band"])}
    )

    assert verdict is not None
    assert verdict.failed_checks == ["clipping"]
    assert verdict.not_assessed == ["speed_steady", "bearing_band"]


def test_a_passing_verdict_is_a_level_with_nothing_listed():
    verdict = verdict_from_assessments({None: stored("high")})

    assert verdict is not None
    assert verdict.trust_level == "High"
    assert verdict.failed_checks == []
    assert verdict.not_assessed == []


def test_a_row_that_is_an_object_rather_than_a_mapping_still_reads():
    # SQLAlchemy hands back mappings here, but a caller passing ORM rows should
    # not silently get None.
    class Row:
        level = "low"
        failed_checks = ["clipping"]
        not_assessed = []

    verdict = verdict_from_assessments({None: Row()})

    assert verdict is not None
    assert verdict.trust_level == "Low"
    assert verdict.failed_checks == ["clipping"]


# ---------------------------------------------------------------------------
# read_quality — the lookup itself
# ---------------------------------------------------------------------------


def test_read_quality_returns_the_stored_verdict(monkeypatch):
    from app.services import quality_storage

    monkeypatch.setattr(
        quality_storage,
        "latest_for_upload",
        lambda db, upload_id: {None: stored("low", ["clipping"])},
    )

    verdict = read_quality(object(), "upload-1")

    assert verdict is not None
    assert verdict.trust_level == "Low"
    assert verdict.failed_checks == ["clipping"]


def test_read_quality_scopes_to_the_channel_it_was_asked_for(monkeypatch):
    from app.services import quality_storage

    monkeypatch.setattr(
        quality_storage,
        "latest_for_upload",
        lambda db, upload_id: {
            None: stored("low", ["clipping"]),
            2: stored("high", channel=2),
        },
    )

    assert read_quality(object(), "upload-1", channel=2).trust_level == "High"
    assert read_quality(object(), "upload-1").trust_level == "Low"


def test_a_lookup_that_fails_reports_unassessed_rather_than_raising(monkeypatch):
    """The verdict is an annotation on the features, not the features.

    An upload whose quality could not be looked up is still an upload worth
    returning; losing the whole response to the thing that grades it would be
    the worst outcome available.
    """
    from app.services import quality_storage

    def exploded(db, upload_id):
        raise RuntimeError("relation data_quality_assessments does not exist")

    monkeypatch.setattr(quality_storage, "latest_for_upload", exploded)

    assert read_quality(object(), "upload-1") is None


# ---------------------------------------------------------------------------
# Narrowing whatever the engine returns
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("High", "High"),
        ("high", "High"),
        ("  LOW  ", "Low"),
        ("Invalid", "Invalid"),
        ("medium", "Medium"),
    ],
)
def test_a_level_is_matched_whatever_its_casing(raw, expected):
    assert normalize_trust_level(raw) == expected


def test_an_enum_member_is_read_by_value_or_name():
    """Engines tend to return enums, and pydantic will not serialise one."""

    class Trust(Enum):
        HIGH = "High"
        SUSPECT = "Low"

    assert normalize_trust_level(Trust.HIGH) == "High"
    assert normalize_trust_level(Trust.SUSPECT) == "Low"

    class ByName(Enum):
        Medium = 2

    assert normalize_trust_level(ByName.Medium) == "Medium"


@pytest.mark.parametrize("raw", [None, "", "  ", "Excellent", "trustworthy", 3, object()])
def test_anything_else_is_not_a_level(raw):
    assert normalize_trust_level(raw) is None


def test_failed_checks_accept_plain_names():
    assert normalize_failed_checks(["clipping", "dc_offset"]) == ["clipping", "dc_offset"]


def test_failed_checks_accept_records_and_keep_the_code():
    # A check reported with its message attached still lists as one name.
    reported = [
        {"code": "clipping", "message": "12% of samples at full scale"},
        {"name": "dc_offset", "severity": "warning"},
    ]
    assert normalize_failed_checks(reported) == ["clipping", "dc_offset"]


def test_failed_checks_drop_blanks_and_repeats():
    # A check listed twice reads as two separate problems.
    assert normalize_failed_checks(["clipping", "clipping", "", None, "  "]) == ["clipping"]


@pytest.mark.parametrize("raw", [None, "clipping", 7])
def test_failed_checks_refuse_anything_that_is_not_a_list(raw):
    # A bare string is the dangerous one: iterating it would list every letter
    # as a failed check.
    assert normalize_failed_checks(raw) == []


def test_the_order_the_engine_reported_is_kept():
    # The engine decides what matters most; this is not the place to re-rank it.
    assert normalize_failed_checks(["c", "a", "b"]) == ["c", "a", "b"]


def test_a_verdict_defaults_to_nothing_listed():
    verdict = QualityVerdict(trust_level="High")
    assert verdict.failed_checks == []
    assert verdict.not_assessed == []
