"""Run the joint detectors over a capture and store what they said — VIK-043.

The detectors learn from the same window the baseline learns from: the same
operating mode, acquisition shape and converter setting. Anything else would
have the two halves of the platform disagreeing about what normal refers to
-- a detector trained across a settings change reports the settings change,
on every capture, forever.

Fitted per capture rather than cached. On this data that is a few
milliseconds per channel and it removes a whole class of problem: a cached
model is a model that can be stale, and a stale anomaly detector is one that
judges today against a machine that no longer exists. If it ever becomes
expensive, caching keyed on (sensor, channel, mode, shape, step, window) is
the change to make -- and every part of that key is a reason the cache would
have to be invalidated anyway.

Never raises.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any, Optional
from uuid import UUID

import numpy as np

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.versions import version_of
from app.ai.detectors import MIN_TRAINING_SAMPLES, run_detectors
from app.services.feature_catalog import INFORMATIONAL

logger = logging.getLogger(__name__)

TABLE = "capture_detector_scores"
# Declared in `app.ai.versions`, not here. Five modules each
# holding their own constant is five places to forget, and
# section 22 turns on no version changing silently.
ENGINE_VERSION = version_of("detectors")

#: Captures to train on. Enough for the model to have seen the shape of the
#: machine's behaviour without reaching back past the last time somebody
#: changed something about it.
TRAINING_WINDOW = 200


def training_matrix(
    db: Session, sensor_id: UUID, channel: int, upload_id: UUID,
    mode_id: Optional[str],
) -> tuple[Optional[np.ndarray], list[str], int]:
    """History for one channel as a matrix, and the feature names behind it.

    Scoped the way the baseline is: same operating mode, same acquisition
    shape, same converter step, quality-excluded captures left out. Only
    features present on *every* capture in the window are kept -- a feature
    missing from some of them would otherwise be filled with a stand-in
    value, and a stand-in is a number the machine never produced.

    Informational features are dropped. They describe the signal rather than
    the machine, and letting them into a joint model means the model learns
    to react to the recording rather than the pump.
    """
    mode_clause = ("AND m.mode_id = :mode" if mode_id else
                   "AND (m.mode_id IS NULL OR m.is_unknown)")
    rows = db.execute(text(f"""
        SELECT f.upload_id, f.feature_code, f.value, u.created_at
          FROM measurement_channel_features f
          JOIN sensor_data_uploads u ON u.id = f.upload_id
          LEFT JOIN data_quality_assessments q
                 ON q.upload_id = f.upload_id AND q.channel = f.channel
          LEFT JOIN capture_operating_modes m ON m.upload_id = f.upload_id
         WHERE f.sensor_id = :s AND f.channel = :c
           AND f.upload_id <> :u
           AND (q.level IS NULL OR q.level <> 'invalid')
           {mode_clause}
         ORDER BY u.created_at DESC
    """), {"s": str(sensor_id), "c": int(channel), "u": str(upload_id),
           **({"mode": mode_id} if mode_id else {})}).fetchall()

    by_upload: dict[str, dict[str, float]] = defaultdict(dict)
    order: list[str] = []
    for upload, code, value, _ in rows:
        key = str(upload)
        if key not in by_upload:
            order.append(key)
        by_upload[key][code] = float(value)

    order = order[:TRAINING_WINDOW]
    if len(order) < MIN_TRAINING_SAMPLES:
        return None, [], len(order)

    shared = set.intersection(*(set(by_upload[u]) for u in order))
    names = sorted(shared - set(INFORMATIONAL))
    if not names:
        return None, [], len(order)

    matrix = np.array([[by_upload[u][n] for n in names] for u in order],
                      dtype=float)
    return matrix, names, len(order)


def persist_detectors(
    db: Session,
    *,
    upload_id: UUID,
    sensor_id: UUID,
    features: dict[tuple[int, str], float],
    mode_id: Optional[str] = None,
) -> dict[str, Any]:
    """Run both detectors on every channel of one capture and store the result."""
    channels = sorted({channel for channel, _ in features})
    written = scored = 0

    try:
        db.execute(text(f"DELETE FROM {TABLE} WHERE upload_id = :u"),
                   {"u": str(upload_id)})
    except Exception:
        logger.exception("Could not clear detector scores for %s", upload_id)

    worst: Optional[dict[str, Any]] = None
    for channel in channels:
        try:
            matrix, names, available = training_matrix(
                db, sensor_id, channel, upload_id, mode_id)
            if matrix is None:
                verdicts = run_detectors([], [], [])
            else:
                reading = [features.get((channel, n)) for n in names]
                if any(v is None for v in reading):
                    # This capture is missing a feature the window has. The
                    # detectors compare like with like or not at all.
                    verdicts = run_detectors([], [], [])
                else:
                    verdicts = run_detectors(matrix, reading, names)
        except Exception:
            logger.exception("Detectors failed on channel %s", channel)
            continue

        for verdict in verdicts:
            try:
                db.execute(text(f"""
                    INSERT INTO {TABLE}
                        (upload_id, sensor_id, channel, method, score,
                         is_scored, raw, drivers, reason, training_samples,
                         mode_id, engine_version)
                    VALUES (:u, :s, :c, :m, :score, :is_scored, :raw,
                            CAST(:drivers AS jsonb), :reason, :n, :mode, :v)
                """), {
                    "u": str(upload_id), "s": str(sensor_id), "c": channel,
                    "m": verdict.method, "score": verdict.value,
                    "is_scored": verdict.scored, "raw": verdict.raw,
                    "drivers": json.dumps(
                        [{"feature": f, "share": round(s, 4)}
                         for f, s in verdict.drivers]),
                    "reason": verdict.reason,
                    "n": available if matrix is not None else None,
                    "mode": mode_id, "v": ENGINE_VERSION,
                })
                written += 1
                if verdict.scored:
                    scored += 1
                    if worst is None or verdict.value > worst["score"]:
                        worst = {"channel": channel, "method": verdict.method,
                                 "score": verdict.value,
                                 "reason": verdict.reason}
            except Exception:
                logger.exception("Could not store %s for channel %s",
                                 verdict.method, channel)

    if worst:
        logger.info("Upload %s joint detectors: worst %s on ch%d at %.0f",
                    upload_id, worst["method"], worst["channel"],
                    worst["score"])
    return {"written": written, "scored": scored, "worst": worst}


def latest_for_upload(db: Session, upload_id: UUID) -> list[dict[str, Any]]:
    rows = db.execute(text(f"""
        SELECT channel, method, score, is_scored, raw, drivers, reason,
               training_samples
          FROM {TABLE} WHERE upload_id = :u
         ORDER BY is_scored DESC, score DESC NULLS LAST, channel, method
    """), {"u": str(upload_id)}).mappings().fetchall()
    return [dict(row) for row in rows]
