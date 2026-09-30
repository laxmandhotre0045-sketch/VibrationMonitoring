"""Naming the fault, and keeping the finding — VIK-053 and VIK-058.

The ranking engine, the evidence structure and the axial penalty were
written and tested before this platform could feed them anything. This is
the wiring: a capture's spectrum becomes a peak list, the machine record
becomes a context, the engine ranks its hypotheses, and each one becomes a
finding that persists.

**A finding evolves; it is not re-created.** Its identity is the machine,
the channel and the fault -- never the capture. Re-loading the same capture
updates the finding it belongs to and does not make a second one, which is
VIK-058's acceptance criterion and the only reason `first_detected_at` can
mean anything. A row per capture would restate the fault every two minutes
and "this has been developing for nine days" would be unanswerable.

**A finding carries what the instrument could not see.** The resolution
verdict travels on every row, because on this gateway the spectrum cannot
separate the outer-race frequency from the third shaft harmonic -- they are
1.58 Hz apart and one bin is 3.60 Hz. Without that recorded, "no bearing
fault found" reads as a healthy machine when it means a blind instrument.

Never raises. A capture whose faults could not be ranked is still a capture,
and its scores and alarms are already stored.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

import numpy as np

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.versions import version_of
from app.ai.fault_resolution import assess_resolution
from app.ai.recommendation import HISTORY_LENGTH, direction_of, recommend
from app.ai.severity import grade
from app.ai.symptoms import detect as detect_symptoms
from app.services.fault_context import (
    context_completeness,
    direction_for_channel,
    machine_context,
    peaks_from_spectrum,
)
from vibcore.signatures import match_faults

logger = logging.getLogger(__name__)

TABLE = "fault_findings"
SYMPTOMS_TABLE = "capture_symptoms"
ACTIONS_TABLE = "fault_recommendations"
# Declared in `app.ai.versions`, not here. Five modules each
# holding their own constant is five places to forget, and
# section 22 turns on no version changing silently.
ENGINE_VERSION = version_of("fault")

#: How many checks `app.ai.symptoms.detect` runs in total. Recorded beside
#: each result so an empty list can be told from a list that could only
#: ever have had two entries in it.
SYMPTOM_CHECKS_TOTAL = 5

#: The checks that need no shaft speed. The other three are written in
#: orders of running speed and cannot be evaluated without one.
SYMPTOM_CHECKS_WITHOUT_SPEED = 2

#: Hypotheses kept per channel. The engine ranks them; below the top few a
#: hypothesis is the rule table reaching, and a screen showing fifteen
#: possible faults per channel tells nobody anything.
TOP_N = 4

#: Engine score below which a hypothesis is not worth recording at all.
#: The engine's own floor is 0.05, which is low enough to surface a rule
#: that matched almost nothing.
MIN_SCORE = 0.20


def _record_symptoms(db: Session, *, upload_id: UUID, sensor_id: UUID,
                     channel: int, symptoms: list[dict[str, Any]],
                     shaft_usable: bool) -> None:
    """Store one channel's observations, whether or not a fault was named.

    Written before the shaft-speed gate on purpose. An earlier version
    detected symptoms inside the fault-ranking loop, which runs only after
    a shaft speed has been established -- and on this gateway one never has
    been, so the whole layer ran zero times in production. VIK-051 exists
    precisely so a capture matching no rule still has something said about
    it, and that is this machine, every time.
    """
    db.execute(text(f"""
        INSERT INTO {SYMPTOMS_TABLE}
            (upload_id, sensor_id, channel, symptoms, shaft_usable,
             checks_run, checks_possible)
        VALUES (:u, :s, :c, CAST(:sym AS jsonb), :usable, :run, :possible)
        ON CONFLICT (upload_id, channel) DO UPDATE SET
            symptoms = EXCLUDED.symptoms,
            shaft_usable = EXCLUDED.shaft_usable,
            checks_run = EXCLUDED.checks_run,
            checks_possible = EXCLUDED.checks_possible
    """), {"u": str(upload_id), "s": str(sensor_id), "c": channel,
           "sym": json.dumps(symptoms), "usable": shaft_usable,
           "run": len(symptoms),
           "possible": (SYMPTOM_CHECKS_TOTAL if shaft_usable
                        else SYMPTOM_CHECKS_WITHOUT_SPEED)})


def _upsert(db: Session, *, sensor_id: UUID, equipment_id: Optional[UUID],
            channel: int, hypothesis: Any, resolution: dict,
            completeness: dict, symptoms: list[dict[str, Any]],
            trustworthy: Optional[bool],
            upload_id: UUID, mode_id: Optional[str],
            now: datetime) -> dict[str, Any]:
    """Create or advance one finding. VIK-058 lives here.

    The existing row is read first because the stage depends on it: a stage
    climbs one step per sighting, so it cannot be computed without knowing
    where it was.
    """
    existing = db.execute(text(f"""
        SELECT id, stage, times_seen, peak_score, peak_stage,
               first_detected_at, score_history
          FROM {TABLE}
         WHERE sensor_id = :s AND channel = :c AND fault_key = :k
    """), {"s": str(sensor_id), "c": channel,
           "k": hypothesis.fault_key}).mappings().fetchone()

    times_seen = (existing["times_seen"] + 1) if existing else 1
    stage = grade(score=hypothesis.score, confidence=hypothesis.confidence,
                  times_seen=times_seen,
                  previous_stage=existing["stage"] if existing else None)

    # Requirement 9.2's "trend direction". `score` and `peak_score` cannot
    # answer it -- one is where the finding is, the other the worst it has
    # been, and neither says which way it is travelling.
    history = list((existing["score_history"] or []) if existing else [])
    history.append(round(float(hypothesis.score), 4))
    history = history[-HISTORY_LENGTH:]
    heading = direction_of(history)

    # Requirement 9.2's "recommended next action" and "whether immediate
    # shutdown is needed", and requirement 14's "how urgent is it".
    action = db.execute(text(f"""
        SELECT action_now, action_planned, check_first
          FROM {ACTIONS_TABLE} WHERE fault_key = :k
    """), {"k": hypothesis.fault_key}).mappings().fetchone()

    advice = recommend(
        stage=stage.stage, confidence=float(hypothesis.confidence),
        direction=heading,
        resolution_usable=resolution.get("usable"),
        capture_trustworthy=trustworthy,
        action_now=action["action_now"] if action else None,
        action_planned=action["action_planned"] if action else None)
    if action and action["check_first"]:
        advice.action += " " + action["check_first"]

    payload = {
        "s": str(sensor_id),
        "e": str(equipment_id) if equipment_id else None,
        "c": channel,
        "key": hypothesis.fault_key,
        "name": hypothesis.name,
        "score": float(hypothesis.score),
        "confidence": float(hypothesis.confidence),
        "stage": stage.stage,
        "severity": stage.severity,
        "mechanism": hypothesis.mechanism or None,
        "evidence": json.dumps([e.as_dict() for e in hypothesis.evidence]),
        "against": json.dumps(
            [e.as_dict() for e in hypothesis.contradicting_evidence]),
        "checks": json.dumps(hypothesis.confirming_checks or []),
        "family": hypothesis.family,
        "history": json.dumps(history),
        "direction": heading.direction,
        "direction_reason": heading.reason,
        "urgency": advice.urgency,
        "proposed_urgency": advice.proposed,
        "urgency_capped": advice.capped,
        "urgency_reason": advice.headline,
        "recommended_action": advice.action,
        "shutdown_advised": advice.shutdown_advised,
        "resolution": json.dumps(resolution),
        "completeness": json.dumps(completeness),
        # The channel's observations, not this fault's. A finding travels
        # alone to whoever reads it and has to carry its own context --
        # the same reason `resolution` is repeated on every row.
        "symptoms": json.dumps(symptoms),
        "upload": str(upload_id),
        "mode": mode_id,
        "now": now,
        "version": ENGINE_VERSION,
    }

    db.execute(text(f"""
        INSERT INTO {TABLE}
            (sensor_id, equipment_id, channel, fault_key, fault_name,
             family, score_history, direction, direction_reason,
             urgency, proposed_urgency, urgency_capped, urgency_reason,
             recommended_action, shutdown_advised,
             score, confidence, stage, severity, mechanism,
             evidence, contradicting_evidence, confirming_checks,
             resolution, context_completeness, symptoms,
             first_detected_at, last_seen_at, times_seen,
             peak_score, peak_stage, first_upload_id, last_upload_id,
             mode_id, engine_version)
        VALUES (:s, :e, :c, :key, :name,
                :family, CAST(:history AS jsonb), :direction,
                :direction_reason, :urgency, :proposed_urgency,
                :urgency_capped, :urgency_reason, :recommended_action,
                :shutdown_advised,
                :score, :confidence, :stage,
                :severity, :mechanism, CAST(:evidence AS jsonb),
                CAST(:against AS jsonb), CAST(:checks AS jsonb),
                CAST(:resolution AS jsonb), CAST(:completeness AS jsonb),
                CAST(:symptoms AS jsonb),
                :now, :now, 1, :score, :stage, :upload, :upload, :mode,
                :version)
        ON CONFLICT (sensor_id, channel, fault_key) DO UPDATE SET
            score = EXCLUDED.score,
            confidence = EXCLUDED.confidence,
            stage = EXCLUDED.stage,
            severity = EXCLUDED.severity,
            mechanism = EXCLUDED.mechanism,
            evidence = EXCLUDED.evidence,
            contradicting_evidence = EXCLUDED.contradicting_evidence,
            confirming_checks = EXCLUDED.confirming_checks,
            resolution = EXCLUDED.resolution,
            context_completeness = EXCLUDED.context_completeness,
            symptoms = EXCLUDED.symptoms,
            family = EXCLUDED.family,
            score_history = EXCLUDED.score_history,
            direction = EXCLUDED.direction,
            direction_reason = EXCLUDED.direction_reason,
            urgency = EXCLUDED.urgency,
            proposed_urgency = EXCLUDED.proposed_urgency,
            urgency_capped = EXCLUDED.urgency_capped,
            urgency_reason = EXCLUDED.urgency_reason,
            recommended_action = EXCLUDED.recommended_action,
            shutdown_advised = EXCLUDED.shutdown_advised,
            last_seen_at = EXCLUDED.last_seen_at,
            times_seen = {TABLE}.times_seen + 1,
            -- The worst it has ever been, kept even as it recovers. A fault
            -- that reached severe and fell back is a different maintenance
            -- history from one that never got past watch, and the current
            -- stage alone cannot tell them apart.
            peak_score = GREATEST({TABLE}.peak_score, EXCLUDED.score),
            peak_stage = CASE
                WHEN EXCLUDED.severity >= COALESCE(
                    array_position(ARRAY['normal','watch',
                        'early_fault_suspected','developing','severe',
                        'critical'], {TABLE}.peak_stage) - 1, 0)
                THEN EXCLUDED.stage ELSE {TABLE}.peak_stage END,
            last_upload_id = EXCLUDED.last_upload_id,
            mode_id = EXCLUDED.mode_id,
            -- Re-found, so it is no longer resolved. first_detected_at is
            -- untouched: this is the same fault continuing, and resetting
            -- it would restart the clock every time it was seen.
            resolved_at = NULL
    """), payload)

    return {
        "fault_key": hypothesis.fault_key, "fault_name": hypothesis.name,
        "channel": channel, "score": round(float(hypothesis.score), 3),
        "confidence": round(float(hypothesis.confidence), 3),
        "stage": stage.stage, "severity": stage.severity,
        "times_seen": times_seen, "rose": stage.rose,
        "new": existing is None, "reason": stage.reason,
        "symptoms": [s["key"] for s in symptoms],
        "family": hypothesis.family, "direction": heading.direction,
        "urgency": advice.urgency, "shutdown_advised": advice.shutdown_advised,
    }


def persist_findings(
    db: Session,
    *,
    upload_id: UUID,
    sensor_id: UUID,
    equipment_id: Optional[UUID],
    channels: dict[int, tuple[np.ndarray, np.ndarray]],
    shaft_hz: Optional[float],
    shaft_usable: bool,
    bearing_orders: Optional[dict[str, Any]] = None,
    sample_rate_hz: Optional[float] = None,
    sample_count: Optional[int] = None,
    mode_id: Optional[str] = None,
    features: Optional[dict[int, dict[str, float]]] = None,
) -> dict[str, Any]:
    """Rank and record the faults this capture suggests, per channel.

    `channels` maps a channel index to its (frequencies, magnitudes), and
    `features` the same index to that channel's scalar features -- the crest
    factor and kurtosis the impacting check reads, and the band energies the
    bearing check reads. Passing them is what makes those two symptoms mean
    anything; without them the spectrum-only symptoms still run.
    """
    now = datetime.now(timezone.utc)
    summary: dict[str, Any] = {
        "findings": [], "channels_examined": 0, "resolution": None,
        "symptoms": {}, "reason": "",
    }

    try:
        context = machine_context(
            db, equipment_id,
            shaft_rpm=(shaft_hz * 60.0) if (shaft_hz and shaft_usable) else None,
            bearing_orders=bearing_orders)
        completeness = context_completeness(context)

        resolution = assess_resolution(
            sample_rate_hz=sample_rate_hz, sample_count=sample_count,
            shaft_hz=shaft_hz if shaft_usable else None,
            bearing_orders=context.bearing_orders,
            vane_pass_order=context.vane_pass_order).as_dict()
        summary["resolution"] = resolution
    except Exception:
        logger.exception("Could not build fault context for upload %s",
                         upload_id)
        summary["reason"] = "The machine context could not be assembled."
        return summary

    # Symptoms first, and for every channel, because they are a property of
    # the capture rather than of any fault and most of this gateway's
    # captures never reach the fault ranking below.
    for channel, (freqs, mags) in sorted(channels.items()):
        try:
            observed = [s.as_dict() for s in detect_symptoms(
                peaks_from_spectrum(
                    freqs, mags,
                    shaft_hz=shaft_hz if shaft_usable else None,
                    direction=direction_for_channel(db, sensor_id, channel)),
                (features or {}).get(channel),
                shaft_hz if shaft_usable else None)]
            summary["symptoms"][channel] = observed
            _record_symptoms(db, upload_id=upload_id, sensor_id=sensor_id,
                             channel=channel, symptoms=observed,
                             shaft_usable=bool(shaft_usable))
        except Exception:
            logger.exception("Symptom detection failed on channel %s", channel)

    if not shaft_usable:
        observed_total = sum(len(v) for v in summary["symptoms"].values())
        summary["reason"] = (
            "No shaft speed was established for this capture, so no order "
            "can be placed on the spectrum and no rule in the table can be "
            "evaluated. Not a clean result -- an unmeasurable one. "
            + (f"{observed_total} symptom(s) were still observed from the "
               f"checks that do not need a speed."
               if observed_total else
               "The two checks that do not need a speed -- impacting and "
               "bearing-band energy -- found nothing either."))
        return summary

    # Whether this capture passed its own quality checks. It caps how
    # urgent any finding from it is allowed to be -- a shutdown
    # recommendation off an untrustworthy reading is the single most
    # expensive thing this platform could get wrong.
    trustworthy: Optional[bool] = None
    try:
        row = db.execute(text("""
            SELECT level FROM data_quality_assessments
             WHERE upload_id = :u AND channel IS NULL
             ORDER BY assessed_at DESC LIMIT 1
        """), {"u": str(upload_id)}).fetchone()
        if row and row[0]:
            # The quality engine grades high / medium / low. Only `low`
            # counts as untrustworthy here: capping on `medium` would hold
            # back every finding this gateway produces, and a cap that is
            # always on is a cap nobody reads.
            trustworthy = str(row[0]).lower() != "low"
    except Exception:
        logger.exception("Could not read data quality for upload %s",
                         upload_id)

    seen_keys: set[tuple[int, str]] = set()
    for channel, (freqs, mags) in sorted(channels.items()):
        try:
            peaks = peaks_from_spectrum(
                freqs, mags, shaft_hz=shaft_hz,
                direction=direction_for_channel(db, sensor_id, channel))
            if not peaks:
                continue
            summary["channels_examined"] += 1

            # Detected above, before the shaft-speed gate, and copied onto
            # each finding so a finding carries its own context wherever it
            # is read -- the same reason `resolution` is repeated.
            symptoms = summary["symptoms"].get(channel, [])

            # Features as well as peaks. Cavitation has no line anywhere
            # in the spectrum -- it is recognised by broadband energy and
            # the absence of harmonics -- so an order-only call can never
            # produce it.
            for hypothesis in match_faults(peaks, context, top_n=TOP_N,
                                           min_score=MIN_SCORE,
                                           features=(features or {}).get(
                                               channel)):
                summary["findings"].append(_upsert(
                    db, sensor_id=sensor_id, equipment_id=equipment_id,
                    channel=channel, hypothesis=hypothesis,
                    resolution=resolution, completeness=completeness,
                    symptoms=symptoms, trustworthy=trustworthy,
                    upload_id=upload_id, mode_id=mode_id, now=now))
                seen_keys.add((channel, hypothesis.fault_key))
        except Exception:
            logger.exception("Fault ranking failed on channel %s", channel)

    _close_unseen(db, sensor_id, seen_keys, now)

    if not summary["findings"]:
        summary["reason"] = (
            "No rule in the table matched this capture."
            + ("" if resolution.get("usable") else
               " That is not evidence the machine is healthy: "
               + (resolution.get("reason") or "")))
    summary["findings"].sort(key=lambda f: -f["severity"])
    return summary


def _close_unseen(db: Session, sensor_id: UUID,
                  seen: set[tuple[int, str]], now: datetime) -> None:
    """Mark findings that were not found this time as resolved.

    Resolved rather than deleted. A fault that appeared for a fortnight and
    went away is a maintenance record, and the row is the only trace that it
    happened.
    """
    try:
        rows = db.execute(text(f"""
            SELECT channel, fault_key FROM {TABLE}
             WHERE sensor_id = :s AND resolved_at IS NULL
        """), {"s": str(sensor_id)}).fetchall()
        for channel, key in rows:
            if (int(channel), key) in seen:
                continue
            db.execute(text(f"""
                UPDATE {TABLE} SET resolved_at = :now
                 WHERE sensor_id = :s AND channel = :c AND fault_key = :k
            """), {"s": str(sensor_id), "c": int(channel), "k": key,
                   "now": now})
    except Exception:
        logger.exception("Could not close unseen findings for %s", sensor_id)


def open_findings(db: Session, sensor_id: UUID) -> list[dict[str, Any]]:
    """What this machine is currently thought to be doing, worst first."""
    rows = db.execute(text(f"""
        SELECT channel, fault_key, fault_name, score, confidence, stage,
               severity, mechanism, evidence, contradicting_evidence,
               confirming_checks, resolution, context_completeness,
               symptoms, family, score_history, direction, direction_reason,
               urgency, proposed_urgency, urgency_capped, urgency_reason,
               recommended_action, shutdown_advised,
               first_detected_at, last_seen_at, times_seen, peak_stage,
               acknowledged_at, acknowledged_by, analyst_verdict
          FROM {TABLE}
         WHERE sensor_id = :s AND resolved_at IS NULL
         ORDER BY severity DESC, score DESC
    """), {"s": str(sensor_id)}).mappings().fetchall()
    return [dict(row) for row in rows]
