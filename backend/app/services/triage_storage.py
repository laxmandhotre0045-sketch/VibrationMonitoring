"""The priority queue and the feedback log, against the database — Phase 4.

`app.ai.priority` and `app.ai.feedback` do the thinking and know nothing
about storage. This is the wiring, and it carries the two rules that the
engines cannot enforce on their own:

**Feedback is appended, never updated.** Section 16.2 says what the
feedback is for, and every one of those uses needs the history rather than
the latest state. An analyst can change their mind; a second analyst can
disagree with the first; the same fault can be rejected in March and
confirmed in September. A mutable verdict column represents none of that,
so the finding carries the most recent verdict as a convenience and the log
is the record.

**Priority is recomputed, not remembered.** It depends on the machine's
criticality, on how well the capture could be trusted, and on what analysts
have said since -- all of which move independently of the fault. A stored
rank that nothing recomputes is a rank that silently goes stale, which is
worse than none because it looks current.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.feedback import (
    NEGATIVE,
    POSITIVE,
    SUPPRESSION_DAYS,
    VERDICTS,
    standing_from,
    suppress,
)
from app.ai.priority import order, rank
from app.ai.recommendation import acceleration_of

logger = logging.getLogger(__name__)

FINDINGS = "fault_findings"
FEEDBACK = "analyst_feedback"
SYMPTOMS = "capture_symptoms"
SCORES = "feature_anomaly_scores"
ALARMS = "feature_alarm_state"


def _feedback_for(db: Session, sensor_id: UUID, channel: int,
                  fault_key: str) -> list[dict[str, Any]]:
    """Every live report about this fault on this machine.

    Retractions are honoured by excluding both the retracting row and the
    row it retracts -- a withdrawn opinion should count for nothing, not
    for something negative.
    """
    rows = [dict(r) for r in db.execute(text(f"""
        SELECT id, verdict, created_at, analyst, retracts_id
          FROM {FEEDBACK}
         WHERE sensor_id = :s AND channel = :c AND fault_key = :k
         ORDER BY created_at
    """), {"s": str(sensor_id), "c": channel, "k": fault_key}
    ).mappings().fetchall()]

    retracted = {r["retracts_id"] for r in rows if r["retracts_id"]}
    return [r for r in rows
            if r["id"] not in retracted and not r["retracts_id"]]


def _machine(db: Session, sensor_id: UUID) -> dict[str, Any]:
    row = db.execute(text("""
        SELECT e.id AS equipment_id, e.machine_name, e.machine_criticality,
               e.safety_impact, e.production_impact, e.last_maintenance_date
          FROM sensor_configurations s
          LEFT JOIN equipment_masters e ON e.id = s.equipment_id
         WHERE s.id = :s
    """), {"s": str(sensor_id)}).mappings().fetchone()
    return dict(row) if row else {}


def _context(db: Session, sensor_id: UUID) -> dict[str, Any]:
    """The per-machine numbers every finding on it shares."""
    upload = db.execute(text("""
        SELECT id FROM sensor_data_uploads WHERE sensor_id = :s
         ORDER BY created_at DESC LIMIT 1
    """), {"s": str(sensor_id)}).scalar()

    peak = None
    symptoms = 0
    quality = None
    if upload:
        peak = db.execute(text(f"""
            SELECT MAX(score) FROM {SCORES}
             WHERE upload_id = :u AND is_scored
        """), {"u": str(upload)}).scalar()
        symptoms = db.execute(text(f"""
            SELECT COALESCE(SUM(jsonb_array_length(symptoms)), 0)
              FROM {SYMPTOMS} WHERE upload_id = :u
        """), {"u": str(upload)}).scalar() or 0
        quality = db.execute(text("""
            SELECT level FROM data_quality_assessments
             WHERE upload_id = :u AND channel IS NULL
             ORDER BY assessed_at DESC LIMIT 1
        """), {"u": str(upload)}).scalar()

    alarms = db.execute(text(f"""
        SELECT COUNT(*) FROM {ALARMS} WHERE sensor_id = :s AND alarming
    """), {"s": str(sensor_id)}).scalar() or 0

    # Section 15.1's "alarm history", separate from the live count.
    # `first_alarmed_at` survives a dip below the line, so a row that has
    # ever alarmed is an episode even if it is quiet now.
    history = db.execute(text(f"""
        SELECT COUNT(*) FROM {ALARMS}
         WHERE sensor_id = :s AND first_alarmed_at IS NOT NULL
    """), {"s": str(sensor_id)}).scalar() or 0

    return {"anomaly_score": float(peak) if peak is not None else None,
            "symptom_count": int(symptoms), "data_quality": quality,
            "active_alarms": int(alarms), "alarm_history": int(history)}


def score_findings(db: Session, sensor_id: UUID) -> list[dict[str, Any]]:
    """Rank every open finding on one machine. Recomputed each time."""
    machine = _machine(db, sensor_id)
    shared = _context(db, sensor_id)
    now = datetime.now(timezone.utc)

    rows = [dict(r) for r in db.execute(text(f"""
        SELECT id, sensor_id, channel, fault_key, fault_name, family, score,
               confidence,
               stage, severity, times_seen, direction, score_history,
               first_detected_at, last_seen_at, recommended_action, urgency,
               shutdown_advised, assigned_to, triage_status,
               suppressed_until, suppressed_at_score, latest_feedback
          FROM {FINDINGS}
         WHERE sensor_id = :s AND resolved_at IS NULL
    """), {"s": str(sensor_id)}).mappings().fetchall()]

    scored = []
    for row in rows:
        history = row["score_history"] or []
        pace = acceleration_of(history)
        reports = _feedback_for(db, sensor_id, row["channel"],
                                row["fault_key"])
        standing = standing_from(reports, now)

        muted = False
        if row["suppressed_until"]:
            until = row["suppressed_until"]
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
            breakout = row["suppressed_at_score"]
            # Strictly greater, matching `Suppression.active_at`. With
            # `>=` a finding whose breakout equals its own score -- which
            # is what happens at the top of the scale -- is never muted.
            muted = now < until and not (
                breakout is not None and float(row["score"]) > breakout)

        verdict = rank(
            severity=int(row["severity"] or 0),
            confidence=float(row["confidence"] or 0.0),
            anomaly_score=shared["anomaly_score"],
            times_seen=int(row["times_seen"] or 1),
            accelerating=(pace["accelerating"] if pace else None),
            direction=row["direction"],
            symptom_count=shared["symptom_count"],
            active_alarms=shared["active_alarms"],
            alarm_history=shared["alarm_history"],
            data_quality=shared["data_quality"],
            criticality=machine.get("machine_criticality"),
            safety_impact=machine.get("safety_impact"),
            production_impact=machine.get("production_impact"),
            last_maintenance=machine.get("last_maintenance_date"),
            suppressed=muted)

        # What analysts have said moves the priority, bounded and decayed.
        if standing.adjustment and verdict.score is not None:
            verdict.score = round(
                max(0.0, min(100.0,
                             verdict.score * (1.0 + standing.adjustment))), 1)
            verdict.reason += " " + standing.reason
            from app.ai.priority import band_for
            if not muted:
                verdict.band = band_for(verdict.score)

        row["priority"] = verdict
        row["standing"] = standing
        row["machine_name"] = machine.get("machine_name")
        scored.append(row)

    ranked = []
    for position, row, verdict in order([(r, r["priority"]) for r in scored]):
        row["rank"] = position
        ranked.append(row)
    return ranked


def persist_priorities(db: Session, sensor_id: UUID) -> int:
    """Store the computed priority on each finding so SQL can order by it."""
    written = 0
    for row in score_findings(db, sensor_id):
        verdict = row["priority"]
        db.execute(text(f"""
            UPDATE {FINDINGS}
               SET priority_score = :score, priority_band = :band,
                   priority_reason = :reason,
                   priority_inputs = CAST(:inputs AS jsonb)
             WHERE id = :id
        """), {"id": str(row["id"]), "score": verdict.score,
               "band": verdict.band, "reason": verdict.reason,
               "inputs": json.dumps({
                   **verdict.inputs,
                   "condition": verdict.condition,
                   "consequence": verdict.consequence,
                   "trust": verdict.trust,
                   "unknowns": verdict.unknowns,
                   "standing": row["standing"].as_dict()})})
        written += 1
    return written


def queue(db: Session, *, limit: int = 50,
          include_suppressed: bool = False) -> list[dict[str, Any]]:
    """The whole plant's priority queue, worst first. Section 15.2."""
    sensors = [r[0] for r in db.execute(text(
        "SELECT id FROM sensor_configurations")).fetchall()]

    everything: list[dict[str, Any]] = []
    for sensor_id in sensors:
        try:
            everything.extend(score_findings(db, sensor_id))
        except Exception:
            logger.exception("Could not rank findings for sensor %s",
                             sensor_id)

    if not include_suppressed:
        everything = [r for r in everything if not r["priority"].suppressed]

    rows = []
    for position, row, verdict in order([(r, r["priority"])
                                         for r in everything][:]):
        if position > limit:
            break
        rows.append({
            "rank": position,
            # Every action a screen can take -- feedback, assignment -- is
            # addressed by finding id, so a queue without it is read-only.
            "finding_id": str(row["id"]),
            "machine_name": row.get("machine_name"),
            "sensor_id": str(row.get("sensor_id") or ""),
            "channel": row["channel"],
            "fault_suspected": row["fault_name"],
            "fault_key": row["fault_key"],
            "family": row["family"],
            "severity": row["severity"],
            "stage": row["stage"],
            "confidence": float(row["confidence"] or 0.0),
            "recommended_action": row["recommended_action"],
            "urgency": row["urgency"],
            "shutdown_advised": row["shutdown_advised"],
            "first_detected_at": row["first_detected_at"],
            "days_since_detected": (
                (datetime.now(timezone.utc) -
                 (row["first_detected_at"].replace(tzinfo=timezone.utc)
                  if row["first_detected_at"].tzinfo is None
                  else row["first_detected_at"])).days
                if row["first_detected_at"] else None),
            "trend_direction": row["direction"],
            "assigned_analyst": row["assigned_to"],
            "status": row["triage_status"],
            "priority_score": verdict.score,
            "priority_band": verdict.band,
            "priority_reason": verdict.reason,
            "unknowns": verdict.unknowns,
            "latest_feedback": row["latest_feedback"],
            "suppressed": verdict.suppressed,
        })
    return rows


def record_feedback(
    db: Session, *,
    finding_id: UUID,
    verdict: str,
    analyst: str,
    note: Optional[str] = None,
    corrected_fault_key: Optional[str] = None,
    corrected_fault_label: Optional[str] = None,
    corrected_severity: Optional[int] = None,
    retracts_id: Optional[UUID] = None,
    suppression_days: int = SUPPRESSION_DAYS,
) -> dict[str, Any]:
    """Append one analyst report, and apply whatever it changes."""
    if verdict not in VERDICTS:
        raise ValueError(f"{verdict!r} is not one of section 16.1's options")

    finding = db.execute(text(f"""
        SELECT id, sensor_id, equipment_id, channel, fault_key, stage,
               severity, score, confidence, engine_version
          FROM {FINDINGS} WHERE id = :id
    """), {"id": str(finding_id)}).mappings().fetchone()
    if finding is None:
        raise LookupError(f"No finding {finding_id}")

    quality = db.execute(text("""
        SELECT q.level FROM data_quality_assessments q
          JOIN sensor_data_uploads u ON u.id = q.upload_id
         WHERE u.sensor_id = :s AND q.channel IS NULL
         ORDER BY q.assessed_at DESC LIMIT 1
    """), {"s": str(finding["sensor_id"])}).scalar()

    now = datetime.now(timezone.utc)
    db.execute(text(f"""
        INSERT INTO {FEEDBACK}
            (sensor_id, equipment_id, channel, fault_key, finding_id,
             verdict, corrected_fault_key, corrected_fault_label,
             corrected_severity, note, engine_stage, engine_severity,
             engine_score, engine_confidence, engine_version, data_quality,
             analyst, created_at, retracts_id)
        VALUES (:s, :e, :c, :k, :f, :v, :ck, :cl, :cs, :n, :stage, :sev,
                :score, :conf, :ver, :q, :a, :now, :r)
    """), {
        "s": str(finding["sensor_id"]),
        "e": str(finding["equipment_id"]) if finding["equipment_id"] else None,
        "c": finding["channel"], "k": finding["fault_key"],
        "f": str(finding["id"]), "v": verdict,
        "ck": corrected_fault_key, "cl": corrected_fault_label,
        "cs": corrected_severity, "n": note,
        "stage": finding["stage"], "sev": finding["severity"],
        "score": finding["score"], "conf": finding["confidence"],
        "ver": finding["engine_version"], "q": quality,
        "a": analyst, "now": now,
        "r": str(retracts_id) if retracts_id else None})

    updates = {"latest_feedback": verdict, "latest_feedback_at": now}
    applied: list[str] = []

    if verdict == "ignore_for_machine":
        if not note:
            raise ValueError(
                "Muting a fault needs a reason. An unexplained mute is "
                "indistinguishable from not monitoring the machine.")
        mute = suppress(current_score=float(finding["score"] or 0.0),
                        analyst=analyst, reason=note, days=suppression_days,
                        now=now)
        updates.update({"suppressed_until": mute.until,
                        "suppressed_by": analyst,
                        "suppressed_reason": mute.reason,
                        "suppressed_at_score": mute.breakout_score})
        applied.append(mute.reason)

    if verdict == "maintenance_confirmed":
        updates["resolved_at"] = now
        updates["triage_status"] = "closed"
        applied.append("The finding is closed: the fault was real and has "
                       "been dealt with.")

    sets = ", ".join(f"{k} = :{k}" for k in updates)
    db.execute(text(f"UPDATE {FINDINGS} SET {sets} WHERE id = :id"),
               {**updates, "id": str(finding["id"])})

    reports = _feedback_for(db, finding["sensor_id"], finding["channel"],
                            finding["fault_key"])
    standing = standing_from(reports, now)

    return {"recorded": verdict, "effect": VERDICTS[verdict]["effect"],
            "learns": VERDICTS[verdict]["learns"], "applied": applied,
            "standing": standing.as_dict()}


def assign(db: Session, *, finding_id: UUID, analyst: Optional[str],
           status: Optional[str] = None) -> dict[str, Any]:
    """Section 15.2's "Assigned analyst" and "Status"."""
    now = datetime.now(timezone.utc)
    if analyst:
        db.execute(text(f"""
            UPDATE {FINDINGS}
               SET assigned_to = :a, assigned_at = :now,
                   triage_status = COALESCE(:st, 'assigned')
             WHERE id = :id
        """), {"a": analyst, "now": now, "st": status,
               "id": str(finding_id)})
    else:
        db.execute(text(f"""
            UPDATE {FINDINGS}
               SET assigned_to = NULL, assigned_at = NULL,
                   triage_status = COALESCE(:st, 'new')
             WHERE id = :id
        """), {"st": status, "id": str(finding_id)})

    row = db.execute(text(f"""
        SELECT assigned_to, assigned_at, triage_status FROM {FINDINGS}
         WHERE id = :id
    """), {"id": str(finding_id)}).mappings().fetchone()
    return dict(row) if row else {}


def feedback_summary(db: Session) -> dict[str, Any]:
    """What the loop has collected, and what it is doing with it.

    Section 16.2 lists five uses. This is how anyone checks whether the
    feedback is actually feeding anything back, rather than accumulating in
    a table nobody reads.
    """
    rows = [dict(r) for r in db.execute(text(f"""
        SELECT verdict, COUNT(*) AS n FROM {FEEDBACK} GROUP BY verdict
    """)).mappings().fetchall()]
    by_verdict = {r["verdict"]: r["n"] for r in rows}

    corrections = [dict(r) for r in db.execute(text(f"""
        SELECT fault_key, corrected_fault_key, corrected_fault_label,
               COUNT(*) AS n
          FROM {FEEDBACK}
         WHERE verdict IN ('wrong_fault_type', 'new_fault_label')
         GROUP BY 1, 2, 3 ORDER BY n DESC LIMIT 20
    """)).mappings().fetchall()]

    # NEGATIVE is a module constant, not user input, so it is inlined --
    # a bound tuple would need expanding=True and buys nothing here.
    _negative = ", ".join(f"'{v}'" for v in NEGATIVE)
    worst = [dict(r) for r in db.execute(text(f"""
        SELECT fault_key, COUNT(*) AS rejections
          FROM {FEEDBACK} WHERE verdict IN ({_negative})
         GROUP BY 1 ORDER BY rejections DESC LIMIT 10
    """)).mappings().fetchall()]

    total = sum(by_verdict.values())
    return {
        "total": total,
        "by_verdict": {v: {"count": by_verdict.get(v, 0), **VERDICTS[v]}
                       for v in VERDICTS},
        "corrections_awaiting_a_rule": corrections,
        "most_rejected_rules": worst,
        "confirmed": sum(by_verdict.get(v, 0) for v in POSITIVE),
        "rejected": sum(by_verdict.get(v, 0) for v in NEGATIVE),
        "reason": (
            "Nothing has been reported yet, so no analyst feedback is "
            "shaping the queue." if not total else
            f"{total} report(s) recorded. Confirmations and rejections move "
            f"the priority of that fault on that machine; corrections are "
            f"kept with what the engine claimed at the time, which is what "
            f"a retraining step will need."),
    }
