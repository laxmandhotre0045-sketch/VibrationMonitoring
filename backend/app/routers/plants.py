from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.crud import plant as crud
from app.database import get_db
from app.dependencies.auth import get_current_user, require_write_access
from app.models.plant import Area, Line, Plant
from app.schemas.plant import (
    AreaCreate,
    AreaOut,
    AreaUpdate,
    LineCreate,
    LineOut,
    LineUpdate,
    PlantCreate,
    PlantDetailOut,
    PlantOut,
    PlantUpdate,
)

router = APIRouter(
    prefix="/api/v1",
    tags=["Plants"],
    dependencies=[Depends(get_current_user)],
)


# ── Serialisation ───────────────────────────────────────────────────────────

def _line_out(line: Line, line_counts: dict) -> LineOut:
    return LineOut(
        id=line.id,
        area_id=line.area_id,
        name=line.name,
        is_active=line.is_active,
        equipment_count=line_counts.get(line.id, 0),
    )


def _area_out(area: Area, area_counts: dict, line_counts: dict) -> AreaOut:
    return AreaOut(
        id=area.id,
        plant_id=area.plant_id,
        name=area.name,
        is_active=area.is_active,
        equipment_count=area_counts.get(area.id, 0),
        lines=[_line_out(line, line_counts) for line in area.lines],
    )


def _plant_out(plant: Plant, plant_counts: dict) -> PlantOut:
    return PlantOut(
        id=plant.id,
        name=plant.name,
        code=plant.code,
        location=plant.location,
        is_active=plant.is_active,
        area_count=len(plant.areas),
        equipment_count=plant_counts.get(plant.id, 0),
        created_at=plant.created_at,
    )


def _plant_detail_out(plant: Plant, db: Session) -> PlantDetailOut:
    plant_counts = crud.equipment_counts_by_plant(db)
    area_counts = crud.equipment_counts_by_area(db)
    line_counts = crud.equipment_counts_by_line(db)
    base = _plant_out(plant, plant_counts)
    return PlantDetailOut(
        **base.model_dump(),
        areas=[_area_out(area, area_counts, line_counts) for area in plant.areas],
    )


# ── Plants ──────────────────────────────────────────────────────────────────

@router.get("/plants", response_model=list[PlantOut])
def list_plants(
    include_inactive: bool = Query(True, description="Include plants marked inactive"),
    db: Session = Depends(get_db),
):
    plants = crud.list_plants(db, include_inactive=include_inactive)
    counts = crud.equipment_counts_by_plant(db)
    return [_plant_out(plant, counts) for plant in plants]


@router.post(
    "/plants",
    response_model=PlantDetailOut,
    status_code=201,
    dependencies=[Depends(require_write_access)],
)
def create_plant(data: PlantCreate, db: Session = Depends(get_db)):
    if crud.get_plant_by_name(db, data.name):
        raise HTTPException(status_code=409, detail=f"Plant '{data.name}' already exists")
    plant = crud.create_plant(db, data.name, data.code, data.location, data.is_active)
    return _plant_detail_out(crud.get_plant(db, plant.id), db)


@router.get("/plants/{plant_id}", response_model=PlantDetailOut)
def get_plant(plant_id: UUID, db: Session = Depends(get_db)):
    plant = crud.get_plant(db, plant_id)
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")
    return _plant_detail_out(plant, db)


@router.patch(
    "/plants/{plant_id}",
    response_model=PlantDetailOut,
    dependencies=[Depends(require_write_access)],
)
def update_plant(plant_id: UUID, data: PlantUpdate, db: Session = Depends(get_db)):
    plant = crud.get_plant(db, plant_id)
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")

    changes = data.model_dump(exclude_unset=True)
    new_name = changes.get("name")
    if new_name:
        clash = crud.get_plant_by_name(db, new_name)
        if clash and clash.id != plant.id:
            raise HTTPException(status_code=409, detail=f"Plant '{new_name}' already exists")

    plant = crud.update_plant(db, plant, changes)
    return _plant_detail_out(crud.get_plant(db, plant.id), db)


@router.delete("/plants/{plant_id}", status_code=204, dependencies=[Depends(require_write_access)])
def delete_plant(plant_id: UUID, db: Session = Depends(get_db)):
    plant = crud.get_plant(db, plant_id)
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")

    in_use = crud.count_equipment_for_plant(db, plant_id)
    if in_use:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Plant '{plant.name}' still has {in_use} equipment record(s). "
                "Move or delete them first, or mark the plant inactive instead."
            ),
        )
    crud.delete_plant(db, plant)


# ── Areas ───────────────────────────────────────────────────────────────────

@router.post(
    "/plants/{plant_id}/areas",
    response_model=AreaOut,
    status_code=201,
    dependencies=[Depends(require_write_access)],
)
def create_area(plant_id: UUID, data: AreaCreate, db: Session = Depends(get_db)):
    if not crud.get_plant(db, plant_id):
        raise HTTPException(status_code=404, detail="Plant not found")
    if crud.get_area_by_name(db, plant_id, data.name):
        raise HTTPException(
            status_code=409, detail=f"Area '{data.name}' already exists in this plant"
        )
    area = crud.create_area(db, plant_id, data.name, data.is_active)
    return _area_out(crud.get_area(db, area.id), {}, {})


@router.patch(
    "/areas/{area_id}", response_model=AreaOut, dependencies=[Depends(require_write_access)]
)
def update_area(area_id: UUID, data: AreaUpdate, db: Session = Depends(get_db)):
    area = crud.get_area(db, area_id)
    if not area:
        raise HTTPException(status_code=404, detail="Area not found")

    changes = data.model_dump(exclude_unset=True)
    new_name = changes.get("name")
    if new_name:
        clash = crud.get_area_by_name(db, area.plant_id, new_name)
        if clash and clash.id != area.id:
            raise HTTPException(
                status_code=409, detail=f"Area '{new_name}' already exists in this plant"
            )

    area = crud.update_area(db, area, changes)
    return _area_out(
        crud.get_area(db, area.id),
        crud.equipment_counts_by_area(db),
        crud.equipment_counts_by_line(db),
    )


@router.delete("/areas/{area_id}", status_code=204, dependencies=[Depends(require_write_access)])
def delete_area(area_id: UUID, db: Session = Depends(get_db)):
    area = crud.get_area(db, area_id)
    if not area:
        raise HTTPException(status_code=404, detail="Area not found")

    in_use = crud.count_equipment_for_area(db, area_id)
    if in_use:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Area '{area.name}' still has {in_use} equipment record(s). "
                "Move or delete them first, or mark the area inactive instead."
            ),
        )
    crud.delete_area(db, area)


# ── Lines ───────────────────────────────────────────────────────────────────

@router.post(
    "/areas/{area_id}/lines",
    response_model=LineOut,
    status_code=201,
    dependencies=[Depends(require_write_access)],
)
def create_line(area_id: UUID, data: LineCreate, db: Session = Depends(get_db)):
    if not crud.get_area(db, area_id):
        raise HTTPException(status_code=404, detail="Area not found")
    if crud.get_line_by_name(db, area_id, data.name):
        raise HTTPException(
            status_code=409, detail=f"Line '{data.name}' already exists in this area"
        )
    line = crud.create_line(db, area_id, data.name, data.is_active)
    return _line_out(line, {})


@router.patch(
    "/lines/{line_id}", response_model=LineOut, dependencies=[Depends(require_write_access)]
)
def update_line(line_id: UUID, data: LineUpdate, db: Session = Depends(get_db)):
    line = crud.get_line(db, line_id)
    if not line:
        raise HTTPException(status_code=404, detail="Line not found")

    changes = data.model_dump(exclude_unset=True)
    new_name = changes.get("name")
    if new_name:
        clash = crud.get_line_by_name(db, line.area_id, new_name)
        if clash and clash.id != line.id:
            raise HTTPException(
                status_code=409, detail=f"Line '{new_name}' already exists in this area"
            )

    line = crud.update_line(db, line, changes)
    return _line_out(line, crud.equipment_counts_by_line(db))


@router.delete("/lines/{line_id}", status_code=204, dependencies=[Depends(require_write_access)])
def delete_line(line_id: UUID, db: Session = Depends(get_db)):
    line = crud.get_line(db, line_id)
    if not line:
        raise HTTPException(status_code=404, detail="Line not found")

    in_use = crud.count_equipment_for_line(db, line_id)
    if in_use:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Line '{line.name}' still has {in_use} equipment record(s). "
                "Move or delete them first, or mark the line inactive instead."
            ),
        )
    crud.delete_line(db, line)
