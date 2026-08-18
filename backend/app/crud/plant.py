"""Plant / area / line registry.

equipment_masters keeps denormalised plant_name / area / line text columns so
existing filters and dashboard grouping do not need a join. Every rename here
rewrites those columns for the affected equipment rows, which is what keeps the
two representations from drifting apart.
"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.models.equipment import Equipment
from app.models.plant import Area, Line, Plant


# ── Lookups ─────────────────────────────────────────────────────────────────

def get_plant(db: Session, plant_id: UUID) -> Optional[Plant]:
    return (
        db.query(Plant)
        .options(selectinload(Plant.areas).selectinload(Area.lines))
        .filter(Plant.id == plant_id)
        .first()
    )


def get_area(db: Session, area_id: UUID) -> Optional[Area]:
    return db.query(Area).options(selectinload(Area.lines)).filter(Area.id == area_id).first()


def get_line(db: Session, line_id: UUID) -> Optional[Line]:
    return db.query(Line).filter(Line.id == line_id).first()


def get_plant_by_name(db: Session, name: str) -> Optional[Plant]:
    return db.query(Plant).filter(func.lower(Plant.name) == name.strip().lower()).first()


def get_area_by_name(db: Session, plant_id: UUID, name: str) -> Optional[Area]:
    return (
        db.query(Area)
        .filter(Area.plant_id == plant_id, func.lower(Area.name) == name.strip().lower())
        .first()
    )


def get_line_by_name(db: Session, area_id: UUID, name: str) -> Optional[Line]:
    return (
        db.query(Line)
        .filter(Line.area_id == area_id, func.lower(Line.name) == name.strip().lower())
        .first()
    )


def resolve_hierarchy(
    db: Session,
    plant_name: Optional[str],
    area_name: Optional[str],
    line_name: Optional[str],
) -> tuple[Optional[UUID], Optional[UUID], Optional[UUID]]:
    """Map the denormalised names an equipment record carries onto registry ids.

    Names are what the equipment payload has always contained, and equipment may
    legitimately name a plant that was never registered, so anything that does
    not match resolves to None rather than raising. A child is only resolved
    when its parent was, which stops an area of the same name in a different
    plant from being picked up by accident.
    """
    plant = get_plant_by_name(db, plant_name) if plant_name else None
    if plant is None:
        return None, None, None

    area = get_area_by_name(db, plant.id, area_name) if area_name else None
    if area is None:
        return plant.id, None, None

    line = get_line_by_name(db, area.id, line_name) if line_name else None
    return plant.id, area.id, line.id if line else None


def list_plants(db: Session, include_inactive: bool = True) -> List[Plant]:
    query = db.query(Plant).options(selectinload(Plant.areas).selectinload(Area.lines))
    if not include_inactive:
        query = query.filter(Plant.is_active.is_(True))
    return query.order_by(Plant.name.asc()).all()


# ── Equipment usage counts ──────────────────────────────────────────────────

def equipment_counts_by_plant(db: Session) -> dict:
    rows = (
        db.query(Equipment.plant_id, func.count(Equipment.id))
        .filter(Equipment.plant_id.isnot(None))
        .group_by(Equipment.plant_id)
        .all()
    )
    return {plant_id: count for plant_id, count in rows}


def equipment_counts_by_area(db: Session) -> dict:
    rows = (
        db.query(Equipment.area_id, func.count(Equipment.id))
        .filter(Equipment.area_id.isnot(None))
        .group_by(Equipment.area_id)
        .all()
    )
    return {area_id: count for area_id, count in rows}


def equipment_counts_by_line(db: Session) -> dict:
    rows = (
        db.query(Equipment.line_id, func.count(Equipment.id))
        .filter(Equipment.line_id.isnot(None))
        .group_by(Equipment.line_id)
        .all()
    )
    return {line_id: count for line_id, count in rows}


def count_equipment_for_plant(db: Session, plant_id: UUID) -> int:
    return db.query(Equipment).filter(Equipment.plant_id == plant_id).count()


def count_equipment_for_area(db: Session, area_id: UUID) -> int:
    return db.query(Equipment).filter(Equipment.area_id == area_id).count()


def count_equipment_for_line(db: Session, line_id: UUID) -> int:
    return db.query(Equipment).filter(Equipment.line_id == line_id).count()


# ── Writes ──────────────────────────────────────────────────────────────────

def create_plant(db: Session, name: str, code, location, is_active: bool) -> Plant:
    plant = Plant(name=name, code=code, location=location, is_active=is_active)
    db.add(plant)
    db.commit()
    db.refresh(plant)
    return plant


def update_plant(db: Session, plant: Plant, data: dict) -> Plant:
    renamed_to = None
    if "name" in data and data["name"] and data["name"] != plant.name:
        renamed_to = data["name"]

    for field, value in data.items():
        setattr(plant, field, value)

    if renamed_to:
        db.query(Equipment).filter(Equipment.plant_id == plant.id).update(
            {Equipment.plant_name: renamed_to}, synchronize_session=False
        )

    db.commit()
    db.refresh(plant)
    return plant


def delete_plant(db: Session, plant: Plant) -> None:
    db.delete(plant)
    db.commit()


def create_area(db: Session, plant_id: UUID, name: str, is_active: bool) -> Area:
    area = Area(plant_id=plant_id, name=name, is_active=is_active)
    db.add(area)
    db.commit()
    db.refresh(area)
    return area


def update_area(db: Session, area: Area, data: dict) -> Area:
    renamed_to = None
    if "name" in data and data["name"] and data["name"] != area.name:
        renamed_to = data["name"]

    for field, value in data.items():
        setattr(area, field, value)

    if renamed_to:
        db.query(Equipment).filter(Equipment.area_id == area.id).update(
            {Equipment.area: renamed_to}, synchronize_session=False
        )

    db.commit()
    db.refresh(area)
    return area


def delete_area(db: Session, area: Area) -> None:
    db.delete(area)
    db.commit()


def create_line(db: Session, area_id: UUID, name: str, is_active: bool) -> Line:
    line = Line(area_id=area_id, name=name, is_active=is_active)
    db.add(line)
    db.commit()
    db.refresh(line)
    return line


def update_line(db: Session, line: Line, data: dict) -> Line:
    renamed_to = None
    if "name" in data and data["name"] and data["name"] != line.name:
        renamed_to = data["name"]

    for field, value in data.items():
        setattr(line, field, value)

    if renamed_to:
        db.query(Equipment).filter(Equipment.line_id == line.id).update(
            {Equipment.line: renamed_to}, synchronize_session=False
        )

    db.commit()
    db.refresh(line)
    return line


def delete_line(db: Session, line: Line) -> None:
    db.delete(line)
    db.commit()
