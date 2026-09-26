"""Persist what each capture's data was worth — VIK-022.

The assessment is stored rather than recomputed on demand, because a finding
recorded last month has to be explainable now. "Confidence reduced due to
poor signal quality" is only auditable if the assessment that reduced it
survives next to it -- and the thresholds are calibrated against this
gateway, so they will move. When they do, an old finding must still show the
judgement that was actually made.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Any, Optional, Sequence
from uuid import UUID

import numpy as np

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.quality import assess_capture
from app.ai.signal_unit import sensitivity_for_channel

logger = logging.getLogger(__name__)

TABLE = "data_quality_assessments"

#: Bumped whenever a threshold changes. Without it, an assessment from
#: before a recalibration cannot be told from one after it.
ENGINE_VERSION = "1"

#: The Beckhoff EL3632 is +/-5 V, 16-bit signed. Converted to g by whatever
#: sensitivity the PLC applied -- which is 100 mV/g on every channel, as the
#: quantisation step in the stored samples shows, whatever the transducers
#: are rated at.
ADC_VOLTS = 5.0
ADC_COUNTS = 32768


#: How much of the gaps between adjacent distinct values must agree before
#: the modal gap is taken as the converter's step rather than a coincidence.
#: Measured on this gateway, the true step accounts for 55% to 75% of the
#: gaps on every channel; unrelated data has no such mode.
QUANTISATION_MODE_SHARE = 0.35

#: How far the declared sensitivity may sit from the one the samples imply
#: before the two are reported as disagreeing. Generous, because the stored
#: CSV rounds to four decimals and that alone moves the implied figure by a
#: couple of percent.
SENSITIVITY_TOLERANCE = 0.10


def measure_quantisation_step(samples: Sequence[float]) -> Optional[float]:
    """The converter's step, read out of the samples themselves.

    A digitised signal can only take values a whole number of counts apart,
    so the gaps between its adjacent distinct values are multiples of one
    count -- and the commonest gap IS one count. That makes the step
    measurable without trusting any configuration.

    Worth measuring because the configuration here is wrong. `gateway/.env`
    declares 500 mV/g on the first two channels, but the step in the stored
    samples is 0.0015 g on all eight, which is 100 mV/g. Whatever the
    transducers are rated at, the PLC divided every channel by 100 -- and
    the quality engine's resolution check is built on the step, so taking
    the declared figure would have made it wrong by five times on two
    channels.

    Returns None when there is no clear mode, which is the honest answer for
    a signal that is not obviously quantised.
    """
    values = np.unique(np.asarray(samples, dtype=float))
    if values.size < 8:
        return None
    gaps = np.round(np.diff(values), 9)
    gaps = gaps[gaps > 0]
    if gaps.size < 4:
        return None
    modal, count = Counter(gaps.tolist()).most_common(1)[0]
    if count / gaps.size < QUANTISATION_MODE_SHARE or modal <= 0:
        return None
    return float(modal)


def sensitivity_from_step(step_g: Optional[float]) -> Optional[float]:
    """The mV/g the device must have applied to produce this step."""
    if not step_g or step_g <= 0:
        return None
    return ADC_VOLTS / ADC_COUNTS / step_g * 1000.0


def converter_scale(sensitivity_mv_per_g: Optional[float]) -> tuple[float, Optional[float]]:
    """Full-scale range and quantisation step in g, or zeros if unknown.

    Both are properties of the converter and the sensitivity applied to it,
    and the checks that need them say so rather than guessing when they are
    absent. A clipping threshold invented without knowing the range is a
    threshold about nothing.
    """
    if not sensitivity_mv_per_g or sensitivity_mv_per_g <= 0:
        return 0.0, None
    volts_per_g = sensitivity_mv_per_g / 1000.0
    return ADC_VOLTS / volts_per_g, ADC_VOLTS / ADC_COUNTS / volts_per_g


def persist_quality(
    db: Session,
    *,
    upload_id: UUID,
    sensor_id: UUID,
    channels: dict[str, list[float]],
    sampling_rate_hz: float,
    expected_samples: Optional[int] = None,
    sensitivity_mv_per_g: Optional[float] = None,
    channel_map: Optional[list[dict[str, Any]]] = None,
    shaft_hz: Optional[float] = None,
) -> dict[str, Any]:
    """Assess every channel and store the result. Returns the summary.

    Never raises. A capture whose quality could not be judged is still a
    capture worth keeping, and losing it to a failure in the thing that
    grades it would be the worst outcome available.

    Sensitivity is resolved per channel, not once for the capture. A gateway
    may legitimately run 500 mV/g on two channels and 100 on the rest --
    that is the whole point of making it configurable -- and those channels
    then have a different range and a different step from each other.
    `channel_map` supplies the per-channel figures; `sensitivity_mv_per_g`
    is the sensor-wide fallback for channels the map does not name.
    """
    warnings: list[str] = []
    overrides: dict[int, dict[str, Any]] = {}
    declared_step: Optional[float] = converter_scale(sensitivity_mv_per_g)[1]
    steps: list[float] = []

    for name, samples in channels.items():
        try:
            index = int(str(name).lstrip("ch"))
        except ValueError:
            continue

        declared, source = sensitivity_for_channel(
            index, channel_map, sensitivity_mv_per_g)
        full_scale_g, step_g = converter_scale(declared)

        # Prefer the step this channel's own samples show over the one its
        # configuration claims. The resolution check is built on the step,
        # and a declared sensitivity wrong by five times makes it wrong by
        # five times -- which is the state this gateway is in.
        measured = measure_quantisation_step(samples)
        if measured:
            steps.append(measured)
            step_g = measured
            implied = sensitivity_from_step(measured)
            if (declared and implied
                    and abs(implied - declared) / declared > SENSITIVITY_TOLERANCE):
                warnings.append(
                    f"Channel {index} is quantised in steps of "
                    f"{measured:.5f} g, which is {implied:.0f} mV/g, but the "
                    f"{source} record declares {declared:g} mV/g. The device "
                    f"applied a different sensitivity from the one recorded, "
                    f"so every value in g on this channel is out by the ratio "
                    f"between them. The measured figure is used for the "
                    f"resolution check."
                )
                logger.warning(
                    "Sensitivity mismatch on upload %s channel %s: samples "
                    "imply %.0f mV/g, %s record says %s",
                    upload_id, index, implied, source, declared)
            if full_scale_g <= 0 and implied:
                full_scale_g = ADC_VOLTS / (implied / 1000.0)

        overrides[index] = {"full_scale_g": full_scale_g,
                            "quantisation_step_g": step_g}

    try:
        summary = assess_capture(
            channels, sampling_rate_hz,
            per_channel_overrides=overrides,
            expected_samples=expected_samples,
            full_scale_g=0.0,
            quantisation_step_g=None,
            shaft_hz=shaft_hz,
        )
    except Exception:
        logger.exception("Quality assessment failed for upload %s", upload_id)
        return {"level": "unknown", "confidence_factor": 1.0,
                "channels": {}, "failed_checks": [], "not_assessed": [],
                "warnings": []}

    rows: list[dict[str, Any]] = [{
        "upload_id": str(upload_id), "sensor_id": str(sensor_id),
        "channel": None,
        "level": summary["level"],
        "confidence_factor": summary["confidence_factor"],
        "failed_checks": json.dumps(summary["failed_checks"]),
        "not_assessed": json.dumps(summary.get("not_assessed", [])),
        "checks": json.dumps([]),
        "step_g": None,
    }]
    for index, assessment in summary["channels"].items():
        rows.append({
            "upload_id": str(upload_id), "sensor_id": str(sensor_id),
            "channel": int(index),
            "level": assessment["level"],
            "confidence_factor": assessment["confidence_factor"],
            "failed_checks": json.dumps(assessment["failed_checks"]),
            "not_assessed": json.dumps(assessment.get("not_assessed", [])),
            "checks": json.dumps(assessment["checks"]),
            # What this channel was really quantised in. A baseline is
            # scoped to it, so switching a channel from 100 mV/g to 500
            # starts a new normal instead of silently invalidating the old
            # one while the system goes on comparing against it.
            "step_g": (overrides.get(int(index), {}) or {}).get(
                "quantisation_step_g"),
        })

    try:
        # Replace rather than append: re-running the engine on a capture is
        # a corrected opinion, not a second one.
        db.execute(text(f"DELETE FROM {TABLE} WHERE upload_id = :u"),
                   {"u": str(upload_id)})
        for row in rows:
            db.execute(text(f"""
                INSERT INTO {TABLE}
                    (upload_id, sensor_id, channel, level, confidence_factor,
                     failed_checks, not_assessed, checks, engine_version,
                     quantisation_step_g)
                VALUES (:upload_id, :sensor_id, :channel, :level,
                        :confidence_factor, CAST(:failed_checks AS jsonb),
                        CAST(:not_assessed AS jsonb), CAST(:checks AS jsonb),
                        :version, :step_g)
            """), {**row, "version": ENGINE_VERSION})
    except Exception:
        logger.exception("Could not store quality assessment for upload %s",
                         upload_id)

    summary["warnings"] = warnings
    # The median across channels, for a caller that wants one number. The
    # per-channel figures are what the checks actually used and they can
    # differ -- reporting one as though it covered the capture is how a
    # 500 mV/g channel comes to be judged against a 100 mV/g step.
    summary["quantisation_step_g"] = float(np.median(steps)) if steps else None
    summary["declared_step_g"] = declared_step
    summary["channel_steps_g"] = {i: o["quantisation_step_g"]
                                  for i, o in sorted(overrides.items())}
    return summary


def latest_for_upload(db: Session, upload_id: UUID) -> dict[str, Any]:
    """The stored assessment, keyed by channel, with None for the capture."""
    rows = db.execute(text(f"""
        SELECT channel, level, confidence_factor, failed_checks,
               not_assessed, checks, engine_version, assessed_at
          FROM {TABLE} WHERE upload_id = :u ORDER BY channel NULLS FIRST
    """), {"u": str(upload_id)}).mappings().fetchall()
    return {row["channel"]: dict(row) for row in rows}
