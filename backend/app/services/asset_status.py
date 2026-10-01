"""Reading and setting the status an expert put on an asset — SNV-STA-01/10.

Two rules carry this module.

**A machine takes the worst of its sensors.** One sensor reading Critical makes
the machine Critical; seven healthy ones do not talk it back down. Reporting
the average, or the most recent, would let a real finding disappear into a
fleet that is mostly fine.

**Until a person overrides it.** An analyst who has seen the spectrum knows
things the sensors do not — that the pump is being replaced on Friday, that the
reading is a mounting artefact. Once they set the machine's status by hand it
stops inheriting, because otherwise the next capture would quietly undo the
judgement they just made. The override is a row, not a flag in someone's head,
so the next analyst can see it was deliberate.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.sensor import SensorConfiguration
from app.models.status import (
    SCOPE_MACHINE,
    SCOPE_SENSOR,
    STATUS_UNKNOWN,
    AssetStatus,
    worst_status,
)


def get_row(db: Session, scope: str, asset_id: UUID) -> Optional[AssetStatus]:
    """The stored row for one asset, or None when nobody has set a status."""
    return (
        db.query(AssetStatus)
        .filter(AssetStatus.scope == scope, AssetStatus.asset_id == asset_id)
        .first()
    )


def set_status(
    db: Session,
    scope: str,
    asset_id: UUID,
    status: str,
    *,
    user_id: Optional[UUID] = None,
    overridden: bool = False,
) -> AssetStatus:
    """Set an asset's status, replacing whatever was there.

    `overridden` is what a machine's status carries when a person set it by
    hand; it is meaningless on a sensor, whose status is always someone's
    judgement and never inherited from anything.
    """
    row = get_row(db, scope, asset_id)
    if row is None:
        row = AssetStatus(scope=scope, asset_id=asset_id)
        db.add(row)

    row.status = status
    row.overridden = overridden
    row.set_by = user_id
    row.set_at = datetime.now(timezone.utc)
    db.flush()
    return row


def clear_override(db: Session, equipment_id: UUID) -> None:
    """Let a machine follow its sensors again.

    The row is kept rather than deleted: the status stays visible until the
    next roll-up, so a machine does not blink to Unknown while somebody is
    looking at it.
    """
    row = get_row(db, SCOPE_MACHINE, equipment_id)
    if row is not None:
        row.overridden = False
        db.flush()


def sensor_statuses(db: Session, equipment_id: UUID) -> dict[UUID, str]:
    """Every sensor on this machine and the status it carries.

    Sensors with no status are included as Unknown. A sensor nobody has judged
    is part of the answer — leaving it out would let a machine look fully
    reviewed when half of it never was.
    """
    sensor_ids = [
        row[0]
        for row in db.query(SensorConfiguration.id)
        .filter(SensorConfiguration.equipment_id == equipment_id)
        .all()
    ]
    if not sensor_ids:
        return {}

    stored = {
        row.asset_id: row.status
        for row in db.query(AssetStatus)
        .filter(AssetStatus.scope == SCOPE_SENSOR, AssetStatus.asset_id.in_(sensor_ids))
        .all()
    }
    return {sensor_id: stored.get(sensor_id, STATUS_UNKNOWN) for sensor_id in sensor_ids}


def resolve_machine_status(db: Session, equipment_id: UUID) -> tuple[str, bool]:
    """A machine's status now, and whether a person set it.

    Returns the override where one exists, otherwise the worst of its sensors.
    A machine with no sensors is Unknown rather than Normal: nothing is
    watching it, which is not the same as nothing being wrong.
    """
    row = get_row(db, SCOPE_MACHINE, equipment_id)
    if row is not None and row.overridden:
        return row.status, True

    statuses = sensor_statuses(db, equipment_id)
    return worst_status(statuses.values()), False


def refresh_machine_status(
    db: Session, equipment_id: UUID, *, user_id: Optional[UUID] = None
) -> AssetStatus:
    """Recompute and store a machine's status from its sensors.

    Does nothing to a machine somebody has overridden — that is the whole point
    of the override. Called after a sensor's status changes, so the machine
    view never lags the judgement behind it.
    """
    row = get_row(db, SCOPE_MACHINE, equipment_id)
    if row is not None and row.overridden:
        return row

    resolved, _ = resolve_machine_status(db, equipment_id)
    return set_status(
        db, SCOPE_MACHINE, equipment_id, resolved, user_id=user_id, overridden=False
    )
