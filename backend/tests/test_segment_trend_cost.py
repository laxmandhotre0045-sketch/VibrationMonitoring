"""Segment trends cost one extraction per segment — VIK-014.

The ticket's acceptance is "output byte-identical; timing recorded before and
after". Timing is not a test -- it varies with the machine -- so what is
pinned here is the thing timing was a proxy for: the number of calls.

The loop used to run codes on the outside and segments on the inside, so
extract_channel_features was called once per code per segment even though one
call already returns every code. The full-record extraction sat inside the
code loop too, and each of those covers the whole record rather than a
thirty-second of it.

Measured before: 330 calls for one channel, 2,640 for an 8-channel capture.
After: 33 and 264.

This matters beyond the wall clock. Phase 1 multiplies the number of features
by five on a pipeline that already blocks a single worker for the length of an
upload, and it is the reason 50 features are affordable at all.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

import app.services.feature_extraction as fe
from app.ai.envelope_features import ENVELOPE_FEATURE_CODES
from app.services.feature_extraction import (
    FEATURE_CODES,
    SEGMENT_COUNT,
    extract_segment_trends,
)

RATE = 50_000.0


@pytest.fixture
def samples():
    rng = np.random.default_rng(0)
    return (rng.normal(size=13_888) * 0.05).tolist()


def count_calls(monkeypatch, samples):
    calls = {"n": 0}
    original = fe.extract_channel_features

    def counting(sample_list, rate, *args, **kwargs):
        # Forwards whatever it is given. The shaft speed was added as a third
        # argument later, and a stub with a fixed signature turns that into a
        # TypeError inside the thing being measured rather than a count.
        calls["n"] += 1
        return original(sample_list, rate, *args, **kwargs)

    monkeypatch.setattr(fe, "extract_channel_features", counting)
    result = extract_segment_trends(samples, RATE)
    return calls["n"], result


def test_one_extraction_per_segment_plus_one_for_the_record(monkeypatch, samples):
    """The exact budget, not an upper bound.

    An upper bound would survive someone reintroducing a second full-record
    extraction, which is half of what this ticket removed.
    """
    n_calls, _ = count_calls(monkeypatch, samples)
    assert n_calls == SEGMENT_COUNT + 1


def test_the_cost_does_not_scale_with_the_number_of_features(monkeypatch, samples):
    """The regression this guards.

    Phase 1 takes FEATURE_CODES from 10 to about 50. The cost must stay flat
    across that, so it is measured at two different code counts and compared
    -- an absolute threshold would not express the property, and an earlier
    version of this test asserted 33 < 10, which is simply false.
    """
    full, _ = count_calls(monkeypatch, samples)

    # Same work, half the codes. If the cost tracks the code count this halves.
    monkeypatch.setattr(fe, "FEATURE_CODES", FEATURE_CODES[: len(FEATURE_CODES) // 2])
    halved, _ = count_calls(monkeypatch, samples)

    assert full == halved, (
        f"{full} extractions with {len(FEATURE_CODES)} codes but {halved} with "
        f"half of them -- the cost is scaling with the feature count again. "
        f"One call already returns every code."
    )


def test_every_code_still_gets_a_full_trend(samples):
    """Cheaper must not mean less -- with one deliberate exception.

    The envelope features (VIK-020) have no per-segment series and are
    absent rather than carried with an empty one. A segment is a
    thirty-second of the capture, and an envelope spectrum of that has lines
    coarser than the gap between any two of this machine's bearing
    frequencies. A trend of unreadable numbers is not a trend.
    """
    result = extract_segment_trends(samples, RATE)
    expected = set(FEATURE_CODES) - set(ENVELOPE_FEATURE_CODES)
    assert set(result) == expected
    assert set(ENVELOPE_FEATURE_CODES).isdisjoint(result)
    for code, payload in result.items():
        assert len(payload["trend_y"]) == len(payload["trend_x"])
        assert len(payload["trend_y"]) == SEGMENT_COUNT
        assert payload["value"] is not None
        assert payload["unit"]


def test_the_trend_values_come_from_the_segments_not_the_whole_record(samples):
    """Fanning out from one extraction per segment must still give each
    segment its own number. Broadcasting the whole-record value across the
    trend would be a cheap way to pass every other test here."""
    result = extract_segment_trends(samples, RATE)
    rms = result["rms"]
    assert len(set(rms["trend_y"])) > 1, "every segment reported the same value"


def test_the_scalar_is_the_whole_record_not_a_segment(samples):
    """The headline value must describe the capture, not its last thirty-second."""
    result = extract_segment_trends(samples, RATE)
    whole = fe.extract_channel_features(samples, RATE)
    for code in result:
        assert result[code]["value"] == pytest.approx(whole[code]["value"])


def test_output_is_reproducible(samples):
    """Same input, same bytes -- the ticket's byte-identical clause, applied
    to the current implementation so a future change has something to
    compare against."""
    first = json.dumps(extract_segment_trends(samples, RATE), sort_keys=True)
    second = json.dumps(extract_segment_trends(samples, RATE), sort_keys=True)
    assert first == second
