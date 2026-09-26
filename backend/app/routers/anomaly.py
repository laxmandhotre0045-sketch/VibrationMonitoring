"""The Phase 2 read surface — VIK-041 to VIK-046.

Everything Phase 2 built wrote to the database and none of it was
reachable: 36,456 scores, 1,984 detector verdicts and 368 tracked features,
with no way to ask for any of them. An engine nobody can query is an engine
nobody can act on, and the frontend work that depends on this could not
start.

Reads are open to any signed-in user. Two things here write, and both change
what the platform will tell somebody next: acknowledging an alarm, and
changing a machine's sensitivity. Those need write access and record who
did it.

**Suppressed findings are returned alongside the ringing ones.** A finding
past the line and held back -- because it has not persisted, or because the
baseline behind it is too thin -- is the single most useful thing to show
somebody who thinks the platform is too quiet. Hiding it would leave them
adjusting a sensitivity profile blind.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.alarm import PROFILES
from app.database import get_db
from app.dependencies.auth import get_current_user, require_write_access
from app.schemas.anomaly import (
    AcknowledgeIn,
    AlarmSummaryOut,
    CaptureScoresOut,
    DetectorScoreOut,
    ScoredCaptureOut,
    SensitivityIn,
    SensitivityOut,
)
from app.services import detector_storage
from app.services.alarm_storage import sensitivity_for, set_profile

router = APIRouter(
    prefix="/api/v1/anomaly",
    tags=["Anomaly"],
    dependencies=[Depends(get_current_user)],
)


#: Band lower bounds, mirroring app.ai.anomaly.BANDS. Imported rather than
#: retyped would be better; it is retyped here only because the router must
#: not depend on the engine for a presentation detail.
_BANDS = ((91, "critical"), (76, "high"), (61, "abnormal"),
          (41, "watch"), (21, "slight"), (0, "normal"))


def _band_for(score: float) -> str:
    for lower, name in _BANDS:
        if score >= lower:
            return name
    return "normal"


def _sensor_of(db: Session, upload_id: UUID) -> UUID:
    sensor_id = db.execute(text(
        "SELECT sensor_id FROM sensor_data_uploads WHERE id = :u"),
        {"u": str(upload_id)}).scalar()
    if sensor_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            f"No capture {upload_id}")
    return sensor_id


# ------------------------------------------------------- scores --------

@router.get("/captures", response_model=list[ScoredCaptureOut])
def scored_captures(
    sensor_id: UUID = Query(...),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """The captures on this machine that have actually been scored.

    A capture picker needs this and cannot work it out for itself. The
    obvious source, `sensor_data_uploads.features_status`, is wrong: on this
    platform 157 uploads say "pending" while 120 of them carry scores,
    because the column is written by the ingest path and the scores were
    also written by backfill scripts that never touched it. Filtering a
    picker on that column hides 116 analysed captures and shows four.

    So this asks the score table, which is the thing being picked from.
    """
    rows = db.execute(text("""
        SELECT s.upload_id, u.created_at,
               COUNT(*) FILTER (WHERE s.is_scored) AS scored,
               COUNT(*) FILTER (WHERE NOT s.is_scored) AS unscored,
               MAX(s.score) AS worst_score,
               m.label AS mode_label
          FROM feature_anomaly_scores s
          JOIN sensor_data_uploads u ON u.id = s.upload_id
          LEFT JOIN capture_operating_modes m ON m.upload_id = s.upload_id
         WHERE s.sensor_id = :s
         GROUP BY s.upload_id, u.created_at, m.label
         ORDER BY u.created_at DESC
         LIMIT :limit
    """), {"s": str(sensor_id), "limit": limit}).mappings().fetchall()

    captures = []
    for row in rows:
        payload = dict(row)
        worst = payload.get("worst_score")
        # The band is derived rather than stored on the row, so the picker
        # and the detail panel can never disagree about which band a score
        # falls in.
        payload["worst_band"] = _band_for(worst) if worst is not None else None
        captures.append(payload)
    return captures




@router.get("/scores", response_model=CaptureScoresOut)
def capture_scores(
    upload_id: UUID = Query(...),
    channel: Optional[int] = Query(None, ge=0),
    scored_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    """How unusual every reading in one capture was.

    `scored_only` is off by default on purpose. The features that could not
    be scored are the honest part of the answer -- a caller that never sees
    them cannot tell "nothing is wrong here" from "nothing has ever been
    learned here", and those need different actions.
    """
    sensor_id = _sensor_of(db, upload_id)

    clauses = ["s.upload_id = :u"]
    params: dict = {"u": str(upload_id)}
    if channel is not None:
        clauses.append("s.channel = :c")
        params["c"] = channel
    if scored_only:
        clauses.append("s.is_scored")

    rows = db.execute(text(f"""
        SELECT s.channel, s.feature_code, s.score, s.band, s.is_scored,
               s.z_score, s.confidence, s.baseline_version, s.mode_id,
               s.reason, s.contributions
          FROM feature_anomaly_scores s
         WHERE {' AND '.join(clauses)}
         ORDER BY s.is_scored DESC, s.score DESC NULLS LAST,
                  s.channel, s.feature_code
    """), params).mappings().fetchall()

    scores = [dict(row) for row in rows]
    mode = db.execute(text("""
        SELECT mode_id, label FROM capture_operating_modes WHERE upload_id = :u
    """), {"u": str(upload_id)}).fetchone()

    return {
        "upload_id": upload_id,
        "sensor_id": sensor_id,
        "scored": sum(1 for s in scores if s["is_scored"]),
        "unscored": sum(1 for s in scores if not s["is_scored"]),
        "mode_id": mode.mode_id if mode else None,
        "mode_label": mode.label if mode else None,
        # The first row, because the query already sorts scored-first then
        # by score. None when nothing could be scored -- which is not the
        # same as a capture whose worst feature scored zero.
        "worst": next((s for s in scores if s["is_scored"]), None),
        "scores": scores,
    }


@router.get("/detectors", response_model=list[DetectorScoreOut])
def capture_detectors(
    upload_id: UUID = Query(...),
    db: Session = Depends(get_db),
):
    """What the two joint detectors made of each channel.

    These look at the whole feature vector at once, which is how they catch
    a combination that no single feature would flag -- every number inside
    its own range while the relationship between them stops making sense.
    Isolation Forest finds captures far from the crowd; PCA residual finds
    captures close to the crowd but in a direction it never occupies.
    """
    _sensor_of(db, upload_id)
    return detector_storage.latest_for_upload(db, upload_id)


# ------------------------------------------------------- alarms --------

@router.get("/alarms", response_model=AlarmSummaryOut)
def alarms(
    sensor_id: UUID = Query(...),
    include_suppressed: bool = Query(True),
    db: Session = Depends(get_db),
):
    """What is ringing on this machine, and what is being held back.

    A single high reading is not an alarm: at this threshold chance alone
    puts about one feature per capture past the line. So the suppressed
    list is not noise being hidden -- it is the evidence somebody needs to
    decide whether this machine's sensitivity is set where they want it.
    """
    equipment_id = db.execute(text(
        "SELECT equipment_id FROM sensor_configurations WHERE id = :s"),
        {"s": str(sensor_id)}).scalar()
    sensitivity = sensitivity_for(db, equipment_id)

    rows = db.execute(text("""
        SELECT channel, feature_code, score, band, confidence, run_length,
               required, first_alarmed_at, last_alarmed_at, acknowledged_at,
               acknowledged_by, reason, alarming, held_back
          FROM feature_alarm_state
         WHERE sensor_id = :s AND (alarming OR held_back IS NOT NULL)
         ORDER BY alarming DESC, score DESC NULLS LAST
    """), {"s": str(sensor_id)}).mappings().fetchall()

    ringing = [dict(r) for r in rows if r["alarming"]]
    suppressed = [dict(r) for r in rows if r["held_back"]]

    return {
        "sensor_id": sensor_id,
        "profile": sensitivity.profile,
        "alarming": len(ringing),
        "held_back": len(suppressed),
        "alarms": ringing,
        "suppressed": suppressed if include_suppressed else [],
    }


@router.post("/alarms/acknowledge", response_model=AlarmSummaryOut,
             dependencies=[Depends(require_write_access)])
def acknowledge(
    payload: AcknowledgeIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Mark one ringing alarm as seen.

    Acknowledging does not silence it. The alarm keeps ringing while the
    condition holds, because the machine has not got better -- what changes
    is that somebody has looked. An acknowledgement that stopped the alarm
    would make "seen" and "resolved" the same word, and they are not.

    It is cleared automatically if the alarm stops and starts again, since
    the person who acknowledged the old one has not seen this one.
    """
    who = next((str(getattr(user, a)) for a in ("email", "username", "name")
                if getattr(user, a, None)), str(getattr(user, "id", "unknown")))

    updated = db.execute(text("""
        UPDATE feature_alarm_state
           SET acknowledged_at = now(), acknowledged_by = :by
         WHERE sensor_id = :s AND channel = :c AND feature_code = :f
           AND alarming
        RETURNING id
    """), {"s": str(payload.sensor_id), "c": payload.channel,
           "f": payload.feature_code, "by": who[:120]}).fetchone()

    if updated is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"{payload.feature_code} on channel {payload.channel} is not "
            f"currently alarming for this sensor. Only a ringing alarm can "
            f"be acknowledged -- there is nothing for an acknowledgement of "
            f"a quiet feature to mean.")
    db.commit()
    return alarms(sensor_id=payload.sensor_id, include_suppressed=True, db=db)


# -------------------------------------------------- sensitivity --------

def _sensitivity_payload(db: Session, equipment_id: UUID) -> dict:
    settings = sensitivity_for(db, equipment_id)
    row = db.execute(text("""
        SELECT expert_overrides, updated_by, updated_at
          FROM ai_sensitivity_settings WHERE equipment_id = :e
    """), {"e": str(equipment_id)}).fetchone()
    return {
        "equipment_id": equipment_id,
        **settings.as_dict(),
        "expert_overrides": (row.expert_overrides if row else {}) or {},
        "updated_by": row.updated_by if row else None,
        "updated_at": row.updated_at if row else None,
    }


@router.get("/sensitivity", response_model=SensitivityOut)
def get_sensitivity(
    equipment_id: UUID = Query(...),
    db: Session = Depends(get_db),
):
    """The machine's sensitivity profile, and the numbers it sets.

    The numbers are returned rather than described, so a settings screen can
    show what choosing a profile will actually do. A machine nobody has
    configured comes back as the recommended default rather than as an
    error: it is being monitored at that setting right now.
    """
    return _sensitivity_payload(db, equipment_id)


@router.put("/sensitivity", response_model=SensitivityOut,
            dependencies=[Depends(require_write_access)])
def put_sensitivity(
    payload: SensitivityIn,
    equipment_id: UUID = Query(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Change how readily this machine raises an alarm.

    Expert values are clamped to bounds rather than rejected, and the bounds
    exist because both extremes look like a working setup from a settings
    page: a threshold of 100 says nothing ever, a persistence of 1 says
    everything always.
    """
    profile = payload.profile.strip().lower()
    if profile not in PROFILES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"{payload.profile!r} is not a sensitivity profile. "
            f"Choose one of: {', '.join(PROFILES)}.")

    who = next((str(getattr(user, a)) for a in ("email", "username", "name")
                if getattr(user, a, None)), str(getattr(user, "id", "unknown")))
    set_profile(db, equipment_id, profile,
                overrides=payload.overrides, updated_by=who[:120])
    db.commit()
    return _sensitivity_payload(db, equipment_id)
