"""Record how unusual each reading was — VIK-041/042 storage.

Stored rather than recomputed, for the reason every other verdict in this
platform is stored: a score is a function of a baseline, and baselines
change. They roll, they are reset, they gain a mode. A score recomputed next
month against a different normal is a different score, and a finding that
said 84 would quietly become 31 with nothing recording that it ever said 84.

`baseline_version` and `mode_id` travel on every row so the comparison can
be reconstructed, and the unscored rows are written too -- a feature nothing
could be said about is a fact worth keeping, and leaving it out would make
"not scored" indistinguishable from "never looked at".

Never raises. A capture whose features could not be scored is still a
capture worth keeping.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.anomaly import Score, score_capture, worst
from app.services.baseline_engine import load_baseline_map
from app.services.feature_catalog import INFORMATIONAL

logger = logging.getLogger(__name__)

TABLE = "feature_anomaly_scores"
ENGINE_VERSION = "1"


def quality_factors(db: Session, upload_id: UUID) -> dict[int, float]:
    """Each channel's trustworthiness, from the stored quality verdict.

    Defaults to 1.0 for a channel nothing assessed rather than to a penalty:
    the capture has not been shown to be poor, and inventing a discount
    would quietly lower every score on a platform where the quality engine
    had not run.
    """
    rows = db.execute(text("""
        SELECT channel, confidence_factor FROM data_quality_assessments
         WHERE upload_id = :u AND channel IS NOT NULL
    """), {"u": str(upload_id)}).fetchall()
    return {int(c): float(f) for c, f in rows if f is not None}


def mode_of(db: Session, upload_id: UUID) -> Optional[str]:
    """The operating mode this capture was in, or None if unknown."""
    mode_id = db.execute(text("""
        SELECT mode_id FROM capture_operating_modes
         WHERE upload_id = :u AND NOT is_unknown
    """), {"u": str(upload_id)}).scalar()
    return str(mode_id) if mode_id else None


def persist_scores(
    db: Session,
    *,
    upload_id: UUID,
    sensor_id: UUID,
    features: dict[tuple[int, str], float],
) -> dict[str, Any]:
    """Score every feature in one capture and store the result."""
    try:
        mode_id = mode_of(db, upload_id)
        baselines = load_baseline_map(db, sensor_id, mode_id=mode_id)
        scores = score_capture(
            features, baselines,
            quality_by_channel=quality_factors(db, upload_id),
            informational=set(INFORMATIONAL),
        )
    except Exception:
        logger.exception("Anomaly scoring failed for upload %s", upload_id)
        return {"scored": 0, "unscored": 0, "worst": None}

    try:
        db.execute(text(f"DELETE FROM {TABLE} WHERE upload_id = :u"),
                   {"u": str(upload_id)})
        for score in scores:
            db.execute(text(f"""
                INSERT INTO {TABLE}
                    (upload_id, sensor_id, channel, feature_code, score, band,
                     is_scored, z_score, baseline_version, mode_id,
                     confidence, contributions, reason, engine_version)
                VALUES (:u, :s, :channel, :code, :score, :band, :is_scored,
                        :z, :version, :mode, :confidence,
                        CAST(:contributions AS jsonb), :reason, :engine)
            """), {
                "u": str(upload_id), "s": str(sensor_id),
                "channel": score.channel, "code": score.feature_code,
                "score": score.value, "band": score.band,
                "is_scored": score.scored, "z": score.z,
                "version": score.baseline_version, "mode": score.mode_id,
                "confidence": score.confidence,
                "contributions": json.dumps(score.contributions),
                "reason": score.reason, "engine": ENGINE_VERSION,
            })
    except Exception:
        logger.exception("Could not store anomaly scores for upload %s",
                         upload_id)

    top = worst(scores)
    summary = {
        "scored": sum(1 for s in scores if s.scored),
        "unscored": sum(1 for s in scores if not s.scored),
        "mode_id": mode_id,
        "worst": top.as_dict() if top else None,
    }
    if top:
        logger.info("Upload %s worst: %s ch%d scored %.0f (%s, confidence "
                    "%.2f)", upload_id, top.feature_code, top.channel,
                    top.value, top.band, top.confidence)
    else:
        logger.info("Upload %s: nothing could be scored -- no learned normal "
                    "for any of its features", upload_id)
    return summary


def latest_for_upload(db: Session, upload_id: UUID) -> list[dict[str, Any]]:
    """Every stored score for one capture, worst first.

    Unscored rows sort last rather than as zero: they are not the least
    unusual readings, they are the ones nothing could be said about.
    """
    rows = db.execute(text(f"""
        SELECT channel, feature_code, score, band, is_scored, z_score,
               confidence, baseline_version, mode_id, reason, contributions
          FROM {TABLE} WHERE upload_id = :u
         ORDER BY is_scored DESC, score DESC NULLS LAST, channel, feature_code
    """), {"u": str(upload_id)}).mappings().fetchall()
    return [dict(row) for row in rows]
