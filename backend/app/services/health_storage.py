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
from app.services.alarm_storage import ALARMS, active_alarms
from app.services.baseline_lifecycle import _IN_FORCE_SQL

logger = logging.getLogger(__name__)

FINDINGS = "fault_findings"
SCORES = "feature_anomaly_scores"
PLOTS = "fault_plot_evidence"
CAPTURE_SYMPTOMS = "capture_symptoms"
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
               times_seen, peak_stage, resolved_at, resolution
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

    verdict = assess(
        findings=findings, anomaly_scores=scores, symptoms=symptoms,
        active_alarms=alarms, trend_rising=trend_rising,
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
