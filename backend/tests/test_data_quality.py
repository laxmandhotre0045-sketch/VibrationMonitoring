"""The trust level on the features response.

The engine that decides trust is VIK-022 and is not in this repository, so
these tests are about the contract rather than the verdicts: that the response
carries both fields, that an unassessed measurement is reported as unassessed
rather than as passing, and that whatever shape the engine eventually returns is
narrowed to the four documented levels before it reaches a caller.

`read_quality` reads the verdict off the upload row, so a stand-in row with
those attributes exercises the real path — the same path a real engine will
light up when it starts writing them.
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
)


class Assessed:
    """An upload row carrying a verdict, as an engine would leave it."""

    def __init__(self, trust_level=None, failed_checks=None):
        self.trust_level = trust_level
        self.failed_checks = failed_checks


class Unassessed:
    """An upload row from before the engine existed: no verdict attributes."""


# ---------------------------------------------------------------------------
# The contract
# ---------------------------------------------------------------------------


def test_the_response_carries_both_fields():
    fields = UploadFeaturesOut.model_fields
    assert "trust_level" in fields
    assert "failed_checks" in fields


def test_the_response_publishes_the_four_levels():
    # The frontend switches on these. A fifth level appearing without a schema
    # change is a value no screen knows how to place.
    schema = UploadFeaturesOut.model_json_schema()
    rendered = str(schema)
    for level in ("High", "Medium", "Low", "Invalid"):
        assert level in rendered, f"{level} is missing from the published schema"
    assert TRUST_LEVELS == ("High", "Medium", "Low", "Invalid")


def test_the_published_endpoint_advertises_both_fields():
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
    assert "failed_checks" in properties
    assert properties["failed_checks"]["items"]["type"] == "string"

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


# ---------------------------------------------------------------------------
# read_quality — the seam VIK-022 plugs into
# ---------------------------------------------------------------------------


def test_an_upload_with_no_verdict_reads_as_none():
    # Every upload in this build, until the engine lands.
    assert read_quality(Unassessed()) is None
    assert read_quality(Assessed()) is None
    assert read_quality(None) is None


def test_a_verdict_on_the_upload_is_read_back():
    verdict = read_quality(Assessed("Low", ["clipping", "short_record"]))

    assert verdict is not None
    assert verdict.trust_level == "Low"
    assert verdict.failed_checks == ["clipping", "short_record"]


def test_a_passing_verdict_is_a_level_with_no_failed_checks():
    # The distinction the whole design rests on: nothing failed, versus nothing
    # ran. Both report an empty list, and only the level tells them apart.
    verdict = read_quality(Assessed("High", []))

    assert verdict is not None
    assert verdict.trust_level == "High"
    assert verdict.failed_checks == []


def test_an_unrecognised_level_is_refused_rather_than_passed_through():
    # A level the contract does not publish would reach a caller with no
    # defined place in the ordering. Better to report nothing.
    assert read_quality(Assessed("Excellent", ["whatever"])) is None


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


def test_a_verdict_defaults_to_no_failed_checks():
    assert QualityVerdict(trust_level="High").failed_checks == []
