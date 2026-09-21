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
from typing import Any, Optional
from uuid import UUID

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
                "channels": {}, "failed_checks": [], "not_assessed": []}

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

    return summary


def latest_for_upload(db: Session, upload_id: UUID) -> dict[str, Any]:
    """The stored assessment, keyed by channel, with None for the capture."""
    rows = db.execute(text(f"""
        SELECT channel, level, confidence_factor, failed_checks,
               not_assessed, checks, engine_version, assessed_at
          FROM {TABLE} WHERE upload_id = :u ORDER BY channel NULLS FIRST
    """), {"u": str(upload_id)}).mappings().fetchall()
    return {row["channel"]: dict(row) for row in rows}
