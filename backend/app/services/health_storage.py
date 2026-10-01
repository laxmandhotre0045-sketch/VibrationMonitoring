"""Gathering what a health score is made of — VIK-055 support.

`app.ai.health` does the arithmetic and knows nothing about the database.
This is the other half: eight inputs, each from a different table, and the
honest reporting of the ones that are not there.

**A missing input is passed through as missing, never as a default.** Every
lookup here can legitimately come back empty -- a machine with no baseline,
a capture whose alarms have not been evaluated, a sensor with no findings --
and the difference between "nothing found" and "nothing looked" is the only
thing a health score has to get right. So the readers below return `None`
where a value is unavailable and the scorer is left to say so, rather than
substituting a zero that would read as good news.

**Also the reason the fault-to-plot table exists.** `plots_for` turns a
finding into the screens that would confirm or refute it, which is what
turns "believe this" into "go and look".
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.health import assess
from app.ai.reliability import assess as assess_reliability
from app.ai.recommendation import acceleration_of
from app.services.alarm_storage import ALARMS, active_alarms
from app.services.baseline_lifecycle import _IN_FORCE_SQL

logger = logging.getLogger(__name__)

FINDINGS = "fault_findings"
SCORES = "feature_anomaly_scores"
PLOTS = "fault_plot_evidence"
CAPTURE_SYMPTOMS = "capture_symptoms"
FEEDBACK_TABLE = "analyst_feedback"
VERSIONS = "baseline_versions"

#: Alarm bands that count as the worst level for health. The alarm table
#: stores the anomaly band rather than a severity word, so the mapping is
#: made here rather than assumed in the scorer.
BAND_SEVERITY = {
    "critical": "critical", "high": "critical",
    "abnormal": "warning", "watch": "warning",
    "slight": "info", "normal": "info",
}


def _scalar(db: Session, sql: str, params: dict) -> Any:
    row = db.execute(text(sql), params).fetchone()
    return row[0] if row else None


def latest_upload(db: Session, sensor_id: UUID) -> Optional[dict[str, Any]]:
    row = db.execute(text("""
        SELECT id, created_at FROM sensor_data_uploads
         WHERE sensor_id = :s ORDER BY created_at DESC LIMIT 1
    """), {"s": str(sensor_id)}).mappings().fetchone()
    return dict(row) if row else None


def sensor_health(db: Session, sensor_id: UUID, *,
                  criticality: Optional[str] = None) -> dict[str, Any]:
    """Score one sensor's machine from everything stored about it."""
    findings = [dict(r) for r in db.execute(text(f"""
        SELECT fault_key, fault_name, channel, stage, severity, confidence,
               times_seen, peak_stage, resolved_at, resolution,
               score_history, direction
          FROM {FINDINGS} WHERE sensor_id = :s
    """), {"s": str(sensor_id)}).mappings().fetchall()]

    upload = latest_upload(db, sensor_id)
    hours: Optional[float] = None
    scores: list[float] = []
    symptoms: list[dict[str, Any]] = []
    resolution_usable: Optional[bool] = None

    if upload:
        created = upload["created_at"]
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600.0

        scores = [float(r[0]) for r in db.execute(text(f"""
            SELECT score FROM {SCORES}
             WHERE upload_id = :u AND is_scored AND score IS NOT NULL
        """), {"u": str(upload["id"])}).fetchall()]

    # Symptoms and the resolution verdict travel on the findings, so they
    # come from whichever finding was written most recently rather than
    # from a second query against the capture.
    for row in findings:
        if row.get("resolved_at") is None and row.get("resolution"):
            verdict = row["resolution"]
            if isinstance(verdict, dict):
                resolution_usable = bool(verdict.get("usable"))
            break

    # From the capture rather than from the findings. Most captures on this
    # gateway produce no finding at all -- no shaft speed means no rule can
    # be evaluated -- and reading symptoms off findings would report none
    # for exactly the machines that have nothing else to go on.
    seen: set[str] = set()
    if upload:
        for row in db.execute(text(f"""
            SELECT symptoms FROM {CAPTURE_SYMPTOMS} WHERE upload_id = :u
        """), {"u": str(upload["id"])}).fetchall():
            for item in (row[0] or []):
                if isinstance(item, dict) and item.get("key") not in seen:
                    seen.add(item["key"])
                    symptoms.append(item)

    alarms = []
    try:
        for alarm in active_alarms(db, sensor_id):
            alarms.append({
                "severity": BAND_SEVERITY.get(
                    str(alarm.get("band") or "").lower(), "info"),
                "band": alarm.get("band"),
                "feature_code": alarm.get("feature_code"),
                "channel": alarm.get("channel"),
                "escalating": alarm.get("escalating"),
            })
    except Exception:
        logger.exception("Could not read alarms for sensor %s", sensor_id)

    has_baseline = bool(_scalar(db, f"""
        SELECT 1 FROM {VERSIONS}
         WHERE sensor_id = :s AND state IN {_IN_FORCE_SQL} LIMIT 1
    """, {"s": str(sensor_id)}))

    captures = _scalar(db, """
        SELECT COUNT(*) FROM sensor_data_uploads WHERE sensor_id = :s
    """, {"s": str(sensor_id)})

    # Whether the machine is getting worse is a question the platform
    # cannot currently answer: the steadiness check needs about ten shaft
    # revolutions per half of the record and this gateway's captures are
    # far shorter. `None` says that, rather than claiming it is steady.
    trend_rising: Optional[bool] = None
    escalating = [a for a in alarms if a.get("escalating")]
    if escalating:
        trend_rising = True

    # Requirement 12.1 lists trend acceleration as its own input, separately
    # from the trend. Read off the worst open finding's score history, which
    # is the only run of comparable numbers this machine keeps.
    accelerating: Optional[bool] = None
    acceleration: Optional[dict[str, Any]] = None
    open_rows = [f for f in findings if f.get("resolved_at") is None
                 and f.get("score_history")]
    if open_rows:
        worst = max(open_rows, key=lambda f: int(f.get("severity") or 0))
        acceleration = acceleration_of(worst["score_history"] or [])
        if acceleration is not None:
            accelerating = bool(acceleration["accelerating"])
            trend_rising = trend_rising or (
                worst.get("direction") == "rising")

    verdict = assess(
        findings=findings, anomaly_scores=scores, symptoms=symptoms,
        active_alarms=alarms, trend_rising=trend_rising,
        trend_accelerating=accelerating, acceleration_detail=acceleration,
        has_baseline=has_baseline, resolution_usable=resolution_usable,
        hours_since_capture=hours,
        captures_seen=int(captures) if captures is not None else None,
        criticality=criticality)

    payload = verdict.as_dict()
    payload["sensor_id"] = str(sensor_id)
    payload["last_upload_at"] = upload["created_at"] if upload else None
    payload["open_findings"] = sum(
        1 for f in findings if f.get("resolved_at") is None)
    return payload


def capture_symptoms(db: Session, sensor_id: UUID,
                     upload_id: Optional[UUID] = None) -> dict[str, Any]:
    """What was observed in a capture's signal, per channel.

    Defaults to the most recent capture. Returns the checks that could run
    beside the ones that fired, because most captures on this gateway can
    run only two of the five -- the other three are written in orders of
    running speed and no shaft speed has ever been established here. An
    empty list from a two-check capture and an empty list from a five-check
    one are different findings.
    """
    if upload_id is None:
        upload = latest_upload(db, sensor_id)
        if not upload:
            return {"sensor_id": str(sensor_id), "upload_id": None,
                    "channels": [], "reason":
                    "No capture exists for this sensor."}
        upload_id = upload["id"]

    rows = [dict(r) for r in db.execute(text(f"""
        SELECT channel, symptoms, shaft_usable, checks_run, checks_possible,
               created_at
          FROM {CAPTURE_SYMPTOMS}
         WHERE upload_id = :u ORDER BY channel
    """), {"u": str(upload_id)}).mappings().fetchall()]

    fired = sum(len(r["symptoms"] or []) for r in rows)
    if not rows:
        reason = ("This capture has not been through symptom detection. "
                  "Nothing has been looked for, which is not the same as "
                  "nothing being there.")
    elif fired:
        reason = (f"{fired} observation(s) across {len(rows)} channel(s).")
    else:
        possible = max((r["checks_possible"] for r in rows), default=0)
        reason = (
            f"None of the {possible} checks that could run on this capture "
            f"found anything."
            + ("" if rows[0]["shaft_usable"] else
               " Three of the five need a shaft speed, and none was "
               "established, so they were not among them."))

    return {"sensor_id": str(sensor_id), "upload_id": str(upload_id),
            "channels": rows, "observations": fired, "reason": reason}


def sensor_reliability(db: Session, sensor_id: UUID, *,
                       criticality: Optional[str] = None,
                       last_maintenance=None) -> dict[str, Any]:
    """Section 12.2: how dependable this machine's record is.

    Distinct from `sensor_health`, which says how it is now. Every input
    here is about what the machine has done over time, because an asset's
    record is not erased by a good morning.
    """
    span = db.execute(text("""
        SELECT COUNT(*), MIN(created_at), MAX(created_at)
          FROM sensor_data_uploads WHERE sensor_id = :s
    """), {"s": str(sensor_id)}).fetchone()
    captures = int(span[0] or 0)
    history_days = None
    if span[1] and span[2]:
        history_days = (span[2] - span[1]).total_seconds() / 86400.0

    # Alarm episodes: features currently ringing plus those that have rung
    # and stood down. `first_alarmed_at` survives a dip below the line, so
    # a row that has ever alarmed is an episode.
    episodes = db.execute(text(f"""
        SELECT COUNT(*) FROM {ALARMS}
         WHERE sensor_id = :s AND first_alarmed_at IS NOT NULL
    """), {"s": str(sensor_id)}).scalar() or 0

    rows = [dict(r) for r in db.execute(text(f"""
        SELECT first_detected_at, resolved_at, peak_stage, score_history
          FROM {FINDINGS} WHERE sensor_id = :s
    """), {"s": str(sensor_id)}).mappings().fetchall()]

    now = datetime.now(timezone.utc)
    open_days = []
    failures = 0
    history: list[float] = []
    for row in rows:
        if row["peak_stage"] in ("severe", "critical"):
            failures += 1
        history.extend(float(v) for v in (row["score_history"] or []))
        if row["resolved_at"] is None and row["first_detected_at"]:
            started = row["first_detected_at"]
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            open_days.append((now - started).total_seconds() / 86400.0)

    repairs = db.execute(text(f"""
        SELECT COUNT(*) FROM {FEEDBACK_TABLE}
         WHERE sensor_id = :s AND verdict = 'maintenance_confirmed'
    """), {"s": str(sensor_id)}).scalar() or 0

    # Operating stress: how much observed running was outside the machine's
    # normal mode. Each capture stands for the interval it represents, so
    # this is a share of captures rather than of clock time.
    outside = observed = None
    try:
        # There is no "this is the normal mode" flag anywhere, so the
        # label carries it. Only captures whose mode was actually
        # identified are counted: a capture the detector could not place is
        # not evidence of stress, it is evidence of not knowing, and
        # folding those in would report every gateway with poor mode
        # detection as a plant under strain.
        modes = db.execute(text("""
            SELECT COUNT(*) FILTER (WHERE label NOT ILIKE '%normal%'),
                   COUNT(*),
                   COUNT(*) FILTER (WHERE is_unknown)
              FROM capture_operating_modes m
              JOIN sensor_data_uploads u ON u.id = m.upload_id
             WHERE u.sensor_id = :s AND NOT m.is_unknown
        """), {"s": str(sensor_id)}).fetchone()
        if modes and modes[1]:
            outside, observed = float(modes[0] or 0), float(modes[1])

        unplaced = db.execute(text("""
            SELECT COUNT(*) FROM capture_operating_modes m
              JOIN sensor_data_uploads u ON u.id = m.upload_id
             WHERE u.sensor_id = :s AND m.is_unknown
        """), {"s": str(sensor_id)}).scalar() or 0
        if unplaced:
            unplaced_note = (
                f"{unplaced} capture(s) could not be placed in any operating "
                f"mode and are excluded from the operating-stress figure "
                f"rather than counted as stress.")
        else:
            unplaced_note = None
    except Exception:
        logger.exception("Operating stress unavailable for %s", sensor_id)
        unplaced_note = None

    verdict = assess_reliability(
        current_health=sensor_health(db, sensor_id).get("score"),
        captures=captures, history_days=history_days,
        alarm_episodes=int(episodes), open_fault_days=open_days,
        repairs=int(repairs), previous_failures=failures,
        last_maintenance=last_maintenance, score_history=history,
        hours_outside_normal_mode=outside, hours_observed=observed,
        criticality=criticality)

    payload = verdict.as_dict()
    if unplaced_note:
        payload["unknowns"] = [*payload.get("unknowns", []), unplaced_note]
    payload["sensor_id"] = str(sensor_id)
    payload["captures"] = captures
    payload["history_days"] = round(history_days, 1) if history_days else None
    return payload


def plots_for(db: Session, fault_key: str) -> list[dict[str, Any]]:
    """Which plots would confirm or refute this fault, best first."""
    rows = db.execute(text(f"""
        SELECT plot_type, rank, what_to_look_for, why_this_plot
          FROM {PLOTS} WHERE fault_key = :k ORDER BY rank
    """), {"k": fault_key}).mappings().fetchall()
    return [dict(row) for row in rows]


def plot_evidence_table(db: Session) -> dict[str, list[dict[str, Any]]]:
    """The whole mapping, grouped by fault. Reference material."""
    rows = db.execute(text(f"""
        SELECT fault_key, plot_type, rank, what_to_look_for, why_this_plot
          FROM {PLOTS} ORDER BY fault_key, rank
    """)).mappings().fetchall()

    table: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        entry = dict(row)
        table.setdefault(entry.pop("fault_key"), []).append(entry)
    return table


#: The feature RUL is tracked against, and the level that counts as the end
#: of useful life.
#:
#: Envelope RMS because a bearing is the failure mode this platform can
#: actually see developing, and the envelope is where it shows first. The
#: threshold is deliberately a multiple of the machine's own learned
#: baseline rather than an absolute number -- an absolute g level means
#: different things on different machines, and the whole platform is built
#: on comparing a machine to itself.
RUL_FEATURE = "envelope_rms"
RUL_THRESHOLD_MULTIPLE = 4.0


def sensor_rul(db: Session, sensor_id: UUID) -> dict[str, Any]:
    """Section 13: remaining useful life, or why it cannot be estimated.

    Tracks one feature against a threshold set from the machine's own
    baseline. Returns the refusal far more often than an estimate, which is
    the correct proportion on a gateway with five days of history.
    """
    from app.ai.rul import estimate

    rows = db.execute(text("""
        SELECT u.created_at, f.value
          FROM measurement_channel_features f
          JOIN sensor_data_uploads u ON u.id = f.upload_id
         WHERE u.sensor_id = :s AND f.feature_code = :c
         ORDER BY u.created_at
    """), {"s": str(sensor_id), "c": RUL_FEATURE}).fetchall()

    history = [(r[0], float(r[1])) for r in rows if r[1] is not None]

    # The threshold, from this machine's own learned normal.
    # Median, not mean. The baselines are built on robust statistics
    # throughout, and mixing in a mean here would compare this machine
    # against a different normal from the one every other score uses.
    baseline = db.execute(text("""
        SELECT median FROM feature_baseline_stats
         WHERE sensor_id = :s AND feature_code = :c
         ORDER BY computed_at DESC LIMIT 1
    """), {"s": str(sensor_id), "c": RUL_FEATURE}).scalar()

    if baseline is None or float(baseline) <= 0:
        return {
            "available": False, "sensor_id": str(sensor_id),
            "points": len(history),
            "reason": (
                "RUL prediction not available: this machine has no learned "
                "baseline for " + RUL_FEATURE + ", so there is no level "
                "that counts as the end of its useful life. A threshold "
                "taken from anywhere else would be describing a different "
                "machine."),
            "missing_inputs": [], "confidence": "none", "reliable": False,
        }

    threshold = float(baseline) * RUL_THRESHOLD_MULTIPLE
    hours = db.execute(text("""
        SELECT COUNT(*) FROM sensor_data_uploads WHERE sensor_id = :s
    """), {"s": str(sensor_id)}).scalar() or 0

    verdict = estimate(
        history=history, threshold=threshold,
        feature_name="envelope RMS",
        # Captures are not running hours, and pretending otherwise would
        # invent a number. Left absent so the estimate says it is missing.
        operating_hours=None,
        maintenance_history=None, failure_history=None,
        has_temperature=False, has_load=False)

    payload = verdict.as_dict()
    payload["sensor_id"] = str(sensor_id)
    payload["feature"] = RUL_FEATURE
    payload["threshold"] = round(threshold, 6)
    payload["threshold_basis"] = (
        f"{RUL_THRESHOLD_MULTIPLE:g}x this machine's own learned median of "
        f"{float(baseline):.6g}")
    payload["captures"] = int(hours)
    return payload
