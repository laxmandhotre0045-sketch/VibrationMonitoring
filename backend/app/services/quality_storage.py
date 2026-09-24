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
    shaft_hz: Optional[float] = None,
) -> dict[str, Any]:
    """Assess every channel and store the result. Returns the summary.

    Never raises. A capture whose quality could not be judged is still a
    capture worth keeping, and losing it to a failure in the thing that
    grades it would be the worst outcome available.
    """
    full_scale_g, step_g = converter_scale(sensitivity_mv_per_g)

    # Prefer the step the samples actually show over the one the
    # configuration claims. The resolution check is built on the step, and a
    # declared sensitivity that is wrong by five times makes it wrong by five
    # times -- which is the state this gateway is in.
    declared_step = step_g
    measured = [measure_quantisation_step(v) for v in channels.values()]
    measured = [m for m in measured if m]
    warnings: list[str] = []
    if measured:
        step_g = float(np.median(measured))
        implied = sensitivity_from_step(step_g)
        if (sensitivity_mv_per_g and implied
                and abs(implied - sensitivity_mv_per_g) / sensitivity_mv_per_g
                > SENSITIVITY_TOLERANCE):
            warnings.append(
                f"The samples are quantised in steps of {step_g:.5f} g, which "
                f"is {implied:.0f} mV/g, but the sensor record declares "
                f"{sensitivity_mv_per_g:g} mV/g. The device applied a "
                f"different sensitivity from the one recorded, so either the "
                f"record or the device is wrong -- and every value in g is "
                f"out by the ratio between them. The measured figure is used "
                f"for the resolution check."
            )
            logger.warning("Sensitivity mismatch on upload %s: samples imply "
                           "%.0f mV/g, record says %s",
                           upload_id, implied, sensitivity_mv_per_g)
        if full_scale_g <= 0 and implied:
            full_scale_g = ADC_VOLTS / (implied / 1000.0)

    try:
        summary = assess_capture(
            channels, sampling_rate_hz,
            expected_samples=expected_samples,
            full_scale_g=full_scale_g,
            quantisation_step_g=step_g,
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
                     failed_checks, not_assessed, checks, engine_version)
                VALUES (:upload_id, :sensor_id, :channel, :level,
                        :confidence_factor, CAST(:failed_checks AS jsonb),
                        CAST(:not_assessed AS jsonb), CAST(:checks AS jsonb),
                        :version)
            """), {**row, "version": ENGINE_VERSION})
    except Exception:
        logger.exception("Could not store quality assessment for upload %s",
                         upload_id)

    summary["warnings"] = warnings
    summary["quantisation_step_g"] = step_g
    summary["declared_step_g"] = declared_step
    return summary


def latest_for_upload(db: Session, upload_id: UUID) -> dict[str, Any]:
    """The stored assessment, keyed by channel, with None for the capture."""
    rows = db.execute(text(f"""
        SELECT channel, level, confidence_factor, failed_checks,
               not_assessed, checks, engine_version, assessed_at
          FROM {TABLE} WHERE upload_id = :u ORDER BY channel NULLS FIRST
    """), {"u": str(upload_id)}).mappings().fetchall()
    return {row["channel"]: dict(row) for row in rows}
