from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.equipment import Equipment
from app.models.sensor import SensorConfiguration
from app.schemas.equipment import EquipmentCreate, EquipmentUpdate, SensorConfigCreate, SensorConfigUpdate
from app.crud import plant as plant_crud


def get_equipment_list(db: Session, page: int = 1, page_size: int = 20,
                       plant_name: Optional[str] = None,
                       machine_type: Optional[str] = None,
                       machine_criticality: Optional[str] = None):
    query = db.query(Equipment)
    if plant_name:
        # Exact (case-insensitive) match: the plant selector supplies values
        # straight from the lookup, and a substring match would leak one plant's
        # equipment into another's view (e.g. "mumbai" matching "navi mumbai").
        query = query.filter(func.lower(Equipment.plant_name) == plant_name.strip().lower())
    if machine_type:
        query = query.filter(Equipment.machine_type == machine_type)
    if machine_criticality:
        query = query.filter(Equipment.machine_criticality == machine_criticality)
    total = query.count()
    items = query.order_by(Equipment.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return total, items


def get_equipment_by_id(db: Session, equipment_id: UUID) -> Optional[Equipment]:
    return db.query(Equipment).filter(Equipment.id == equipment_id).first()


def get_equipment_by_machine_id(db: Session, machine_id: str) -> Optional[Equipment]:
    return db.query(Equipment).filter(Equipment.machine_id == machine_id).first()



def _apply_hierarchy_links(db: Session, equipment: Equipment) -> None:
    """Point the equipment at the registry rows its plant/area/line names name.

    The names are the authoritative input — that is what the form submits and
    what every existing filter reads — so the ids are derived from them on every
    write. An unregistered plant simply leaves the links null, which is the same
    state migration 012 left rows in that it could not match.
    """
    equipment.plant_id, equipment.area_id, equipment.line_id = plant_crud.resolve_hierarchy(
        db, equipment.plant_name, equipment.area, equipment.line
    )


def create_equipment(db: Session, data: EquipmentCreate) -> Equipment:
    sensors_data = data.sensors or []
    equipment_data = data.model_dump(exclude={"sensors"})
    db_equipment = Equipment(**equipment_data)
    _apply_hierarchy_links(db, db_equipment)
    db.add(db_equipment)
    db.flush()
    for sensor in sensors_data:
        db_sensor = SensorConfiguration(equipment_id=db_equipment.id, **sensor.model_dump())
        db.add(db_sensor)
    db.commit()
    db.refresh(db_equipment)
    return db_equipment


def update_equipment(db: Session, equipment_id: UUID, data: EquipmentUpdate) -> Optional[Equipment]:
    db_equipment = get_equipment_by_id(db, equipment_id)
    if not db_equipment:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_equipment, field, value)
    if {"plant_name", "area", "line"} & update_data.keys():
        _apply_hierarchy_links(db, db_equipment)
    db.commit()
    db.refresh(db_equipment)
    return db_equipment


def delete_equipment(db: Session, equipment_id: UUID) -> bool:
    db_equipment = get_equipment_by_id(db, equipment_id)
    if not db_equipment:
        return False
    db.delete(db_equipment)
    db.commit()
    return True


def update_image_path(db: Session, equipment_id: UUID, image_path: str) -> Optional[Equipment]:
    db_equipment = get_equipment_by_id(db, equipment_id)
    if not db_equipment:
        return None
    db_equipment.equipment_image_path = image_path
    db.commit()
    db.refresh(db_equipment)
    return db_equipment


# Sensor CRUD

def get_sensors_by_equipment(db: Session, equipment_id: UUID) -> List[SensorConfiguration]:
    return db.query(SensorConfiguration).filter(SensorConfiguration.equipment_id == equipment_id).all()


def get_sensor_by_id(db: Session, sensor_id: UUID) -> Optional[SensorConfiguration]:
    return db.query(SensorConfiguration).filter(SensorConfiguration.id == sensor_id).first()


def get_sensor_by_device_id(db: Session, device_id: str) -> Optional[SensorConfiguration]:
    return (
        db.query(SensorConfiguration)
        .filter(SensorConfiguration.device_id == device_id)
        .first()
    )


def create_sensor(db: Session, equipment_id: UUID, data: SensorConfigCreate) -> SensorConfiguration:
    db_sensor = SensorConfiguration(equipment_id=equipment_id, **data.model_dump())
    db.add(db_sensor)
    db.commit()
    db.refresh(db_sensor)
    return db_sensor


def update_sensor(db: Session, sensor_id: UUID, data: SensorConfigUpdate) -> Optional[SensorConfiguration]:
    db_sensor = get_sensor_by_id(db, sensor_id)
    if not db_sensor:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(db_sensor, field, value)
    db.commit()
    db.refresh(db_sensor)
    return db_sensor


def delete_sensor(db: Session, sensor_id: UUID) -> bool:
    db_sensor = get_sensor_by_id(db, sensor_id)
    if not db_sensor:
        return False
    db.delete(db_sensor)
    db.commit()
    return True


def compute_ai_readiness(equipment: Equipment) -> dict:
    sensor_coverage = len(equipment.sensors) > 0
    checks = {
        "machine_train_configured": equipment.machine_train_configured or False,
        "asset_status_set": equipment.asset_status not in (None, ""),
        "sensor_coverage": sensor_coverage,
        "bearing_database_mapped": equipment.bearing_database_mapped or False,
        "operating_mode_configured": (
            equipment.operating_speed_min is not None and
            equipment.operating_speed_max is not None
        ),
    }
    score = int(sum(checks.values()) / len(checks) * 100)
    return {"equipment_id": equipment.id, "score_percent": score, **checks}
