"""The learned normal, and how much it is worth — VIK-026, VIK-027.

Separate from `/api/v1/baselines`, which owns the nominated reference
capture and keeps that job. Two different things called "baseline" on one
path would be a permanent source of confusion, and the roadmap already
records what conflating them cost: the only baseline this platform had was a
copy of the very file being compared against it.

Reads are open to any signed-in user. Writes change what "normal" means for
a machine, and every finding recorded afterwards is judged against the
result, so they need write access and they record who asked.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user, require_write_access
from app.schemas.learned_baseline import (
    BaselineHealthOut,
    BaselineOperationOut,
    BaselineResetIn,
    BaselineRollIn,
    BaselineWriteIn,
    FeatureHealthOut,
    VersionListOut,
)
from app.services import baseline_lifecycle as lifecycle
from app.services.baseline_engine import reset_baseline, roll_baseline
from app.services.baseline_health import feature_health, sensor_health
from app.services.feature_catalog import FEATURE_DEFINITIONS

router = APIRouter(
    prefix="/api/v1/learned-baselines",
    tags=["Learned baselines"],
    dependencies=[Depends(get_current_user)],
)


def _who(user) -> str:
    """Whoever asked, in whatever form the user record offers.

    Recorded on the version so a baseline change six months old can be
    accounted for. Falls back to the id rather than to "unknown": a change
    nobody is attached to is the thing the version history exists to
    prevent.
    """
    for attribute in ("email", "username", "name"):
        value = getattr(user, attribute, None)
        if value:
            return str(value)[:120]
    return str(getattr(user, "id", "unknown"))[:120]


def _refuse(error: lifecycle.LifecycleError) -> HTTPException:
    """A lifecycle rule broken is the caller's problem, not a server fault.

    409 rather than 400: the request was well formed and the rule is about
    the state the baseline is in, which the caller can resolve -- by thawing
    a frozen baseline, or by starting a version instead of rolling one that
    does not exist.
    """
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))


# ------------------------------------------------------------- reads ---

@router.get("/health", response_model=BaselineHealthOut)
def get_baseline_health(
    sensor_id: UUID = Query(...),
    db: Session = Depends(get_db),
):
    """How much the baseline in force for this sensor is worth.

    Always answers. A sensor with no baseline returns `available: false`
    with the reason, in the same shape as one that has a good baseline, so
    the caller reads one field rather than branching on the response.
    """
    return sensor_health(db, sensor_id,
                         expected_feature_count=len(FEATURE_DEFINITIONS))


@router.get("/health/feature", response_model=FeatureHealthOut)
def get_feature_baseline_health(
    sensor_id: UUID = Query(...),
    channel: int = Query(..., ge=0),
    feature_code: str = Query(..., min_length=1, max_length=64),
    db: Session = Depends(get_db),
):
    """The same question about one feature on one channel.

    What a finding needs to defend itself: the exact baseline it was judged
    against, how many captures went into it, and whether its percentiles
    can be trusted.
    """
    return feature_health(db, sensor_id, channel, feature_code)


@router.get("/versions", response_model=VersionListOut)
def list_baseline_versions(
    sensor_id: UUID = Query(...),
    db: Session = Depends(get_db),
):
    """Every version this sensor has had, newest first.

    Superseded versions are listed, not hidden. A finding recorded against
    v1 is explained by v1, and a history that showed only the current
    version would make that impossible.
    """
    return {
        "sensor_id": sensor_id,
        "in_force": lifecycle.in_force(db, sensor_id),
        "versions": lifecycle.history(db, sensor_id),
    }


# ------------------------------------------------------------ writes ---

@router.post("/reset", response_model=BaselineOperationOut,
             dependencies=[Depends(require_write_access)])
def reset(
    payload: BaselineResetIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Start a new version, learn it, and put it in force.

    Never edits the version it replaces. A finding recorded three months ago
    was judged against a particular normal, and stays explainable only
    because that normal still exists, unchanged.

    A version that learns nothing is not activated: retiring a working
    baseline in favour of an empty one would leave the sensor with no normal
    at all. The response says so in `reason`.
    """
    result = reset_baseline(
        db, payload.sensor_id,
        reason=payload.reason, created_by=_who(user),
        days=payload.days, activate=payload.activate)
    db.commit()
    return result


@router.post("/roll", response_model=BaselineOperationOut,
             dependencies=[Depends(require_write_access)])
def roll(
    payload: BaselineRollIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Recompute the baseline in force from the current window.

    The routine update. Refused on a frozen baseline, which is the point of
    freezing rather than a failure of it.
    """
    try:
        result = roll_baseline(db, payload.sensor_id, days=payload.days)
    except lifecycle.LifecycleError as error:
        db.rollback()
        raise _refuse(error)
    db.commit()
    return result


@router.post("/freeze", response_model=VersionListOut,
             dependencies=[Depends(require_write_access)])
def freeze(
    payload: BaselineWriteIn,
    db: Session = Depends(get_db),
):
    """Stop the baseline in force from learning, without retiring it.

    Worth doing when somebody is willing to vouch for a period. A normal
    that keeps learning from a machine that is slowly degrading follows it
    down, and the degradation never becomes anomalous.
    """
    try:
        lifecycle.freeze(db, payload.sensor_id, reason=payload.reason)
    except lifecycle.LifecycleError as error:
        db.rollback()
        raise _refuse(error)
    db.commit()
    return {
        "sensor_id": payload.sensor_id,
        "in_force": lifecycle.in_force(db, payload.sensor_id),
        "versions": lifecycle.history(db, payload.sensor_id),
    }


@router.post("/thaw", response_model=VersionListOut,
             dependencies=[Depends(require_write_access)])
def thaw(
    payload: BaselineWriteIn,
    db: Session = Depends(get_db),
):
    """Let the baseline in force roll again."""
    try:
        lifecycle.thaw(db, payload.sensor_id)
    except lifecycle.LifecycleError as error:
        db.rollback()
        raise _refuse(error)
    db.commit()
    return {
        "sensor_id": payload.sensor_id,
        "in_force": lifecycle.in_force(db, payload.sensor_id),
        "versions": lifecycle.history(db, payload.sensor_id),
    }
