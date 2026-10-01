"""Setting and reading the status an expert put on a machine or sensor.

SNV-STA-01 (the seven values, set per sensor and machine) and SNV-STA-10
(a machine inherits the worst of its sensors, and can be overridden).

Reading a machine's status never writes. A GET that quietly recomputed and
stored would make the value depend on who looked at it last, which is the
opposite of an auditable judgement.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status as http
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.dependencies.auth import get_current_user, require_admin
from app.models.sensor import SensorConfiguration
from app.models.status import SCOPE_MACHINE, SCOPE_SENSOR
from app.models.user import User
from app.schemas.status import AssetStatusOut, AssetStatusSet, MachineStatusOut
from app.services import asset_status as status_service

router = APIRouter(prefix="/api/v1/status", tags=["status"])


def _out(scope: str, asset_id: UUID, row) -> AssetStatusOut:
    """One asset's status, or the honest absence of one.

    A row that does not exist is reported as Unknown rather than omitted:
    nobody has judged this asset, and a caller must be able to tell that from
    "judged and found Normal".
    """
    if row is None:
        return AssetStatusOut(scope=scope, asset_id=asset_id, status="Unknown")
    return AssetStatusOut(
        scope=scope,
        asset_id=asset_id,
        status=row.status,
        overridden=row.overridden,
        set_by=row.set_by,
        set_at=row.set_at,
    )


@router.get("/machines/{equipment_id}", response_model=MachineStatusOut)
def get_machine_status(
    equipment_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> MachineStatusOut:
    """A machine's status now, with the sensors it came from."""
    if crud.get_equipment_by_id(db, equipment_id) is None:
        raise HTTPException(status_code=404, detail="Machine not found")

    resolved, overridden = status_service.resolve_machine_status(db, equipment_id)
    row = status_service.get_row(db, SCOPE_MACHINE, equipment_id)

    sensors = [
        AssetStatusOut(scope=SCOPE_SENSOR, asset_id=sensor_id, status=value)
        for sensor_id, value in status_service.sensor_statuses(db, equipment_id).items()
    ]

    return MachineStatusOut(
        scope=SCOPE_MACHINE,
        asset_id=equipment_id,
        status=resolved,
        overridden=overridden,
        set_by=row.set_by if row is not None else None,
        set_at=row.set_at if row is not None else None,
        sensors=sensors,
    )


@router.put("/machines/{equipment_id}", response_model=MachineStatusOut)
def set_machine_status(
    equipment_id: UUID,
    payload: AssetStatusSet,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> MachineStatusOut:
    """Set a machine's status by hand, overriding the roll-up.

    `override: false` releases it back to following its sensors — the way an
    analyst undoes a judgement without having to guess what the sensors say.
    """
    if crud.get_equipment_by_id(db, equipment_id) is None:
        raise HTTPException(status_code=404, detail="Machine not found")

    if payload.override:
        status_service.set_status(
            db,
            SCOPE_MACHINE,
            equipment_id,
            payload.status,
            user_id=current_user.id,
            overridden=True,
        )
    else:
        status_service.clear_override(db, equipment_id)
        status_service.refresh_machine_status(db, equipment_id, user_id=current_user.id)

    db.commit()
    return get_machine_status(equipment_id, db=db, _=current_user)


@router.get("/sensors/{sensor_id}", response_model=AssetStatusOut)
def get_sensor_status(
    sensor_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> AssetStatusOut:
    if crud.get_sensor_by_id(db, sensor_id) is None:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return _out(SCOPE_SENSOR, sensor_id, status_service.get_row(db, SCOPE_SENSOR, sensor_id))


@router.put("/sensors/{sensor_id}", response_model=AssetStatusOut)
def set_sensor_status(
    sensor_id: UUID,
    payload: AssetStatusSet,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> AssetStatusOut:
    """Set a sensor's status, then roll its machine up.

    The roll-up runs here rather than on read so the machine view never lags
    the judgement behind it, and so the stored machine status is the one that
    was true when somebody acted.
    """
    sensor = crud.get_sensor_by_id(db, sensor_id)
    if sensor is None:
        raise HTTPException(status_code=404, detail="Sensor not found")

    row = status_service.set_status(
        db, SCOPE_SENSOR, sensor_id, payload.status, user_id=current_user.id
    )
    if sensor.equipment_id is not None:
        status_service.refresh_machine_status(
            db, sensor.equipment_id, user_id=current_user.id
        )

    db.commit()
    db.refresh(row)
    return _out(SCOPE_SENSOR, sensor_id, row)
