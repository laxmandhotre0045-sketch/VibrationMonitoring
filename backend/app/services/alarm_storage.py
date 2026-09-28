"""Turn scores into alarms, and remember when each one started — VIK-044/046.

The decision itself is `app.ai.alarm`; this reads the score history it needs,
applies the machine's own sensitivity setting, and keeps the one fact that
cannot be recomputed: when a fault first started ringing.

That fact matters more than it looks. Recomputing the start from the score
history gives the start of the *current* run, so a fault that dipped below
the line for one capture and came back would have its history quietly reset.
"Getting worse since Tuesday" would become "since this morning", and the
first is the most useful sentence this platform can produce.

Never raises. A capture whose alarms could not be evaluated is still a
capture, and its scores are already stored.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.alarm import AlarmVerdict, Sensitivity, evaluate_capture, resolve

logger = logging.getLogger(__name__)

SETTINGS = "ai_sensitivity_settings"
ALARMS = "feature_alarm_state"
SCORES = "feature_anomaly_scores"

#: How far back to look for the run. A few more than the longest persistence
#: any profile asks for, so the run can always be established without
#: reading a sensor's whole history on every capture.
HISTORY_DEPTH = 25


def sensitivity_for(db: Session, equipment_id: Optional[UUID]) -> Sensitivity:
    """The machine's sensitivity setting, or the recommended default.

    A machine nobody has configured gets Balanced rather than the most eager
    setting. Defaulting to Early Warning would make every unconfigured
    machine the noisiest thing on the plant, which is how a platform teaches
    its users to ignore it.
    """
    if equipment_id is None:
        return resolve(None)
    try:
        row = db.execute(text(f"""
            SELECT profile, expert_overrides FROM {SETTINGS}
             WHERE equipment_id = :e
        """), {"e": str(equipment_id)}).fetchone()
    except Exception:
        logger.exception("Could not read the sensitivity setting for %s",
                         equipment_id)
        return resolve(None)
    if row is None:
        return resolve(None)
    return resolve(row.profile, row.expert_overrides or {})


def score_histories(
    db: Session, sensor_id: UUID, depth: int = HISTORY_DEPTH
) -> dict[tuple[int, str], list[Optional[float]]]:
    """Recent scores per feature, newest first.

    Ordered by the capture's own timestamp rather than by when it was
    scored: a backfill scores old captures today, and ordering by the
    scoring time would read the machine's history backwards.

    Unscored captures come back as None and stay in the sequence. Dropping
    them would join two runs across a gap in the evidence, letting a fault
    seen twice months apart ring as though it had been steady throughout.
    """
    rows = db.execute(text(f"""
        SELECT s.channel, s.feature_code, s.score
          FROM (
            SELECT sc.channel, sc.feature_code, sc.score, u.created_at,
                   ROW_NUMBER() OVER (
                       PARTITION BY sc.channel, sc.feature_code
                       ORDER BY u.created_at DESC) AS depth
              FROM {SCORES} sc
              JOIN sensor_data_uploads u ON u.id = sc.upload_id
             WHERE sc.sensor_id = :s
          ) s
         WHERE s.depth <= :depth
         ORDER BY s.channel, s.feature_code, s.depth
    """), {"s": str(sensor_id), "depth": int(depth)}).fetchall()

    histories: dict[tuple[int, str], list[Optional[float]]] = {}
    for channel, code, score in rows:
        histories.setdefault((int(channel), code), []).append(
            float(score) if score is not None else None)
    return histories


def current_scores(db: Session, upload_id: UUID) -> dict[tuple[int, str], dict]:
    rows = db.execute(text(f"""
        SELECT channel, feature_code, score, band, confidence
          FROM {SCORES} WHERE upload_id = :u
    """), {"u": str(upload_id)}).mappings().fetchall()
    return {(int(r["channel"]), r["feature_code"]): dict(r) for r in rows}


def capture_stability(db: Session, upload_id: UUID) -> Optional[str]:
    """How the shaft speed behaved during this capture.

    Read from the operating-mode verdict, which took it from the quality
    engine. None where nothing assessed it -- and None is not "steady": the
    steadiness check stands down on records too short to judge, and treating
    that as steady would let a capture taken during a speed change escalate
    as though the machine had been holding one speed.
    """
    try:
        return db.execute(text("""
            SELECT stability FROM capture_operating_modes WHERE upload_id = :u
        """), {"u": str(upload_id)}).scalar()
    except Exception:
        logger.exception("Could not read stability for upload %s", upload_id)
        return None


def _store(db: Session, sensor_id: UUID, upload_id: UUID,
           verdict: AlarmVerdict, now: datetime) -> None:
    """Write one feature's alarm state, preserving when it first rang."""
    db.execute(text(f"""
        INSERT INTO {ALARMS}
            (sensor_id, channel, feature_code, alarming, escalating,
             cond_repetition, cond_rising, cond_steady_speed, cond_trustworthy,
             stability, run_length, required,
             score, band, confidence, held_back, reason, last_upload_id,
             first_alarmed_at, last_alarmed_at, updated_at)
        VALUES (:s, :channel, :code, :alarming, :escalating,
                :c_rep, :c_rise, :c_steady, :c_trust,
                :stability, :run, :required, :score,
                :band, :confidence, :held_back, :reason, :upload,
                CASE WHEN :alarming THEN :now ELSE NULL END,
                CASE WHEN :alarming THEN :now ELSE NULL END, :now)
        ON CONFLICT (sensor_id, channel, feature_code) DO UPDATE SET
            alarming = EXCLUDED.alarming,
            escalating = EXCLUDED.escalating,
            cond_repetition = EXCLUDED.cond_repetition,
            cond_rising = EXCLUDED.cond_rising,
            cond_steady_speed = EXCLUDED.cond_steady_speed,
            cond_trustworthy = EXCLUDED.cond_trustworthy,
            stability = EXCLUDED.stability,
            run_length = EXCLUDED.run_length,
            required = EXCLUDED.required,
            score = EXCLUDED.score,
            band = EXCLUDED.band,
            confidence = EXCLUDED.confidence,
            held_back = EXCLUDED.held_back,
            reason = EXCLUDED.reason,
            last_upload_id = EXCLUDED.last_upload_id,
            -- Kept across a dip below the line. This is the whole reason
            -- the row exists: recomputing it from the scores would give the
            -- start of the current run, not of the fault.
            first_alarmed_at = CASE
                WHEN EXCLUDED.alarming
                 THEN COALESCE({ALARMS}.first_alarmed_at, EXCLUDED.first_alarmed_at)
                ELSE NULL END,
            last_alarmed_at = CASE
                WHEN EXCLUDED.alarming THEN EXCLUDED.last_alarmed_at
                ELSE {ALARMS}.last_alarmed_at END,
            -- An alarm that stops and starts again is a new alarm, and
            -- somebody who acknowledged the old one has not seen this.
            acknowledged_at = CASE
                WHEN EXCLUDED.alarming AND {ALARMS}.alarming
                 THEN {ALARMS}.acknowledged_at
                ELSE NULL END,
            acknowledged_by = CASE
                WHEN EXCLUDED.alarming AND {ALARMS}.alarming
                 THEN {ALARMS}.acknowledged_by
                ELSE NULL END,
            updated_at = EXCLUDED.updated_at
    """), {
        "s": str(sensor_id), "channel": verdict.channel,
        "code": verdict.feature_code, "alarming": verdict.alarming,
        "escalating": verdict.escalating,
        "c_rep": verdict.conditions.repetition,
        "c_rise": verdict.conditions.rising,
        "c_steady": verdict.conditions.steady_speed,
        "c_trust": verdict.conditions.trustworthy,
        "stability": verdict.stability,
        "run": verdict.run_length, "required": verdict.required,
        "score": verdict.score, "band": verdict.band,
        "confidence": verdict.confidence, "held_back": verdict.held_back,
        "reason": verdict.reason, "upload": str(upload_id), "now": now,
    })


def persist_alarms(
    db: Session,
    *,
    upload_id: UUID,
    sensor_id: UUID,
    equipment_id: Optional[UUID] = None,
) -> dict[str, Any]:
    """Evaluate every feature's alarm state after a capture has been scored."""
    try:
        sensitivity = sensitivity_for(db, equipment_id)
        histories = score_histories(db, sensor_id)
        if not histories:
            return {"alarming": 0, "held_back": 0, "quiet": 0,
                    "profile": sensitivity.profile, "alarms": []}
        verdicts = evaluate_capture(histories, current_scores(db, upload_id),
                                    sensitivity,
                                    capture_stability(db, upload_id))
    except Exception:
        logger.exception("Alarm evaluation failed for upload %s", upload_id)
        return {"alarming": 0, "held_back": 0, "quiet": 0,
                "profile": None, "alarms": []}

    now = datetime.now(timezone.utc)
    try:
        for verdict in verdicts:
            _store(db, sensor_id, upload_id, verdict, now)
    except Exception:
        logger.exception("Could not store alarm state for upload %s", upload_id)

    ringing = [v for v in verdicts if v.alarming]
    summary = {
        "profile": sensitivity.profile,
        "alarming": len(ringing),
        "escalating": sum(1 for v in verdicts if v.escalating),
        "held_back": sum(1 for v in verdicts if v.held_back),
        "quiet": sum(1 for v in verdicts
                     if not v.alarming and not v.held_back),
        "alarms": [v.as_dict() for v in ringing[:20]],
    }
    if ringing:
        logger.warning(
            "Upload %s: %d feature(s) alarming at the %s setting, worst %s "
            "ch%d at %.0f", upload_id, len(ringing), sensitivity.profile,
            ringing[0].feature_code, ringing[0].channel, ringing[0].score or 0)
    return summary


def active_alarms(db: Session, sensor_id: UUID) -> list[dict[str, Any]]:
    """What is ringing on this machine now, worst first."""
    rows = db.execute(text(f"""
        SELECT channel, feature_code, score, band, confidence, run_length,
               required, first_alarmed_at, last_alarmed_at, acknowledged_at,
               acknowledged_by, reason, escalating, stability,
               cond_repetition, cond_rising, cond_steady_speed,
               cond_trustworthy
          FROM {ALARMS}
         WHERE sensor_id = :s AND alarming
         ORDER BY escalating DESC, score DESC NULLS LAST
    """), {"s": str(sensor_id)}).mappings().fetchall()
    return [dict(row) for row in rows]


def set_profile(db: Session, equipment_id: UUID, profile: str, *,
                overrides: Optional[dict] = None,
                updated_by: Optional[str] = None) -> Sensitivity:
    """Set a machine's sensitivity profile and return what is now in force."""
    import json

    db.execute(text(f"""
        INSERT INTO {SETTINGS} (equipment_id, profile, expert_overrides,
                                updated_by, updated_at)
        VALUES (:e, :p, CAST(:o AS jsonb), :by, now())
        ON CONFLICT (equipment_id) DO UPDATE SET
            profile = EXCLUDED.profile,
            -- Kept when the profile is switched away and back, so somebody
            -- who tries Balanced for a week does not lose their tuning.
            expert_overrides = CASE
                WHEN EXCLUDED.expert_overrides = '{{}}'::jsonb
                 THEN {SETTINGS}.expert_overrides
                ELSE EXCLUDED.expert_overrides END,
            updated_by = EXCLUDED.updated_by,
            updated_at = EXCLUDED.updated_at
    """), {"e": str(equipment_id), "p": profile,
           "o": json.dumps(overrides or {}), "by": updated_by})
    return sensitivity_for(db, equipment_id)
