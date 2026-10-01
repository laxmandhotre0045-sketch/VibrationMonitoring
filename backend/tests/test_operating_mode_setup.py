"""Where a machine's operating bands come from — VIK-039 setup.

The detector refuses to guess what load a machine was under, which reads
like "somebody must now characterise all 26 machines before anything
works". For a fixed-speed machine that is not true: the operating range is
already on the equipment record, and turning it into one band is reading a
field rather than guessing.

The two things worth testing are what it refuses to do. It does not slice a
speed range into low/medium/high, because those are loads and not speeds --
a pump at part load and full load sits at the same rpm, so the three bands
would be one operating state wearing three labels, and each baseline would
be built from a third of the data for nothing. And it does not band on a
range that cannot be a speed: one row in this database holds 55 to 85
against a nameplate of 1480, which is Hz written into an rpm column.
"""

from __future__ import annotations

import pytest

from app.ai.operating_mode import detect_mode
from app.services.operating_mode_setup import (
    NAMEPLATE_MARGIN,
    RANGE_MARGIN,
    propose_band,
)


def test_a_recorded_operating_range_becomes_one_band():
    """The live pump: rated 1480, recorded 1440-1500."""
    band = propose_band(1480.0, 1440.0, 1500.0)
    assert band is not None
    assert band["label"] == "normal_running"
    assert band["rpm_min"] == pytest.approx(1440 * (1 - RANGE_MARGIN), abs=0.1)
    assert band["rpm_max"] == pytest.approx(1500 * (1 + RANGE_MARGIN), abs=0.1)
    assert band["source"] == "configured"


def test_the_band_is_widened_so_the_machine_stays_in_its_own_baseline():
    """The recorded range is what the machine is specified to do, not what
    it was measured doing. A capture at 1435 rpm on a pump specified 1440 to
    1500 is the same machine doing the same thing, and sending it to unknown
    would exclude it from its own baseline."""
    band = propose_band(1480.0, 1440.0, 1500.0)
    assert band["rpm_min"] < 1440.0
    assert band["rpm_max"] > 1500.0


def test_a_nameplate_alone_is_enough():
    band = propose_band(1480.0, None, None)
    assert band["rpm_min"] == pytest.approx(1480 * (1 - NAMEPLATE_MARGIN), abs=0.1)
    assert band["rpm_max"] == pytest.approx(1480 * (1 + NAMEPLATE_MARGIN), abs=0.1)
    assert "no operating range is recorded" in band["notes"]


def test_nothing_on_the_record_means_no_band():
    """The honest answer for a machine nobody has characterised. The
    detector then reports unknown with a reason, which is better than
    banding against a number nobody supplied."""
    assert propose_band(None, None, None) is None


def test_a_range_that_cannot_be_a_speed_is_refused():
    """One equipment row holds 55-85 against a nameplate of 1480 -- Hz
    written into an rpm column. Banding on it would send every capture to
    unknown while the machine looked configured, which is the worst of both:
    no baseline, and nothing saying why."""
    assert propose_band(1480.0, 55.0, 85.0) is None


def test_a_range_is_not_sliced_into_load_bands():
    """Three thirds of a speed range are not three loads. A fixed-speed pump
    at part load and full load sits in the same third, so the labels would
    describe one operating state three times and split its history three
    ways for nothing."""
    band = propose_band(1480.0, 1440.0, 1500.0)
    assert band["label"] == "normal_running"
    assert "low_load" not in band["notes"] or "would produce" in band["notes"]
    # One band, not a list of them.
    assert isinstance(band, dict)


def test_the_derived_band_actually_classifies_a_real_capture():
    """End to end on the live pump's real numbers: 24.67 Hz is 1480 rpm."""
    from app.ai.operating_mode import ModeBand

    band = propose_band(1480.0, 1440.0, 1500.0)
    verdict = detect_mode(
        [ModeBand("m", band["label"], band["rpm_min"], band["rpm_max"])],
        shaft_hz=24.67, shaft_usable=True, overall_level_g=0.0065,
        stability="steady")

    assert verdict.label == "normal_running"
    assert verdict.is_unknown is False
    assert verdict.confidence > 0.9, (
        "the nameplate speed should sit near the centre of a band derived "
        "from that machine's own operating range"
    )


def test_a_capture_well_outside_the_band_is_still_unknown():
    """Deriving a band must not become a way of accepting everything."""
    from app.ai.operating_mode import ModeBand

    band = propose_band(1480.0, 1440.0, 1500.0)
    verdict = detect_mode(
        [ModeBand("m", band["label"], band["rpm_min"], band["rpm_max"])],
        shaft_hz=97.21, shaft_usable=True, overall_level_g=0.0065)

    assert verdict.is_unknown is True, (
        "97.21 Hz is 5832 rpm -- four times this pump's speed, and the "
        "number the estimator returns when it has failed"
    )
