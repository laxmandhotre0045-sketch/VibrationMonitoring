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

from app.ai.fault_resolution import assess_resolution
from app.ai.severity import grade
from app.services.fault_context import (
    context_completeness,
    direction_for_channel,
    machine_context,
    peaks_from_spectrum,
)
from vibcore.signatures import match_faults

logger = logging.getLogger(__name__)

TABLE = "fault_findings"
ENGINE_VERSION = "1"

#: Hypotheses kept per channel. The engine ranks them; below the top few a
#: hypothesis is the rule table reaching, and a screen showing fifteen
#: possible faults per channel tells nobody anything.
TOP_N = 4

#: Engine score below which a hypothesis is not worth recording at all.
#: The engine's own floor is 0.05, which is low enough to surface a rule
#: that matched almost nothing.
MIN_SCORE = 0.20


def _upsert(db: Session, *, sensor_id: UUID, equipment_id: Optional[UUID],
            channel: int, hypothesis: Any, resolution: dict,
            completeness: dict, upload_id: UUID, mode_id: Optional[str],
            now: datetime) -> dict[str, Any]:
    """Create or advance one finding. VIK-058 lives here.

    The existing row is read first because the stage depends on it: a stage
    climbs one step per sighting, so it cannot be computed without knowing
    where it was.
    """
    existing = db.execute(text(f"""
        SELECT id, stage, times_seen, peak_score, peak_stage, first_detected_at
          FROM {TABLE}
         WHERE sensor_id = :s AND channel = :c AND fault_key = :k
    """), {"s": str(sensor_id), "c": channel,
           "k": hypothesis.fault_key}).mappings().fetchone()

    times_seen = (existing["times_seen"] + 1) if existing else 1
    stage = grade(score=hypothesis.score, confidence=hypothesis.confidence,
                  times_seen=times_seen,
                  previous_stage=existing["stage"] if existing else None)

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
        "resolution": json.dumps(resolution),
        "completeness": json.dumps(completeness),
        "upload": str(upload_id),
        "mode": mode_id,
        "now": now,
        "version": ENGINE_VERSION,
    }

    db.execute(text(f"""
        INSERT INTO {TABLE}
            (sensor_id, equipment_id, channel, fault_key, fault_name,
             score, confidence, stage, severity, mechanism,
             evidence, contradicting_evidence, confirming_checks,
             resolution, context_completeness,
             first_detected_at, last_seen_at, times_seen,
             peak_score, peak_stage, first_upload_id, last_upload_id,
             mode_id, engine_version)
        VALUES (:s, :e, :c, :key, :name, :score, :confidence, :stage,
                :severity, :mechanism, CAST(:evidence AS jsonb),
                CAST(:against AS jsonb), CAST(:checks AS jsonb),
                CAST(:resolution AS jsonb), CAST(:completeness AS jsonb),
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
) -> dict[str, Any]:
    """Rank and record the faults this capture suggests, per channel.

    `channels` maps a channel index to its (frequencies, magnitudes).
    """
    now = datetime.now(timezone.utc)
    summary: dict[str, Any] = {
        "findings": [], "channels_examined": 0, "resolution": None,
        "reason": "",
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

    if not shaft_usable:
        summary["reason"] = (
            "No shaft speed was established for this capture, so no order "
            "can be placed on the spectrum and no rule in the table can be "
            "evaluated. Not a clean result -- an unmeasurable one.")
        return summary

    seen_keys: set[tuple[int, str]] = set()
    for channel, (freqs, mags) in sorted(channels.items()):
        try:
            peaks = peaks_from_spectrum(
                freqs, mags, shaft_hz=shaft_hz,
                direction=direction_for_channel(db, sensor_id, channel))
            if not peaks:
                continue
            summary["channels_examined"] += 1

            for hypothesis in match_faults(peaks, context, top_n=TOP_N,
                                           min_score=MIN_SCORE):
                summary["findings"].append(_upsert(
                    db, sensor_id=sensor_id, equipment_id=equipment_id,
                    channel=channel, hypothesis=hypothesis,
                    resolution=resolution, completeness=completeness,
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
               first_detected_at, last_seen_at, times_seen, peak_stage,
               acknowledged_at, acknowledged_by, analyst_verdict
          FROM {TABLE}
         WHERE sensor_id = :s AND resolved_at IS NULL
         ORDER BY severity DESC, score DESC
    """), {"s": str(sensor_id)}).mappings().fetchall()
    return [dict(row) for row in rows]
