import os
import shutil
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.config import settings
from app import crud
from app.schemas.equipment import (
    EquipmentCreate, EquipmentUpdate, EquipmentOut,
    PaginatedEquipment, AIReadinessOut,
    SensorConfigCreate, SensorConfigUpdate, SensorConfigOut,
)

router = APIRouter(prefix="/api/v1/equipment", tags=["Equipment"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


# ── Equipment CRUD ──────────────────────────────────────────────────────────

@router.post("/", response_model=EquipmentOut, status_code=201)
def create_equipment(data: EquipmentCreate, db: Session = Depends(get_db)):
    import logging
    logging.getLogger("uvicorn").info(f"[CREATE_EQUIPMENT] plant_name={repr(data.plant_name)} area={repr(data.area)} machine_name={repr(data.machine_name)} machine_type={repr(data.machine_type)}")
    if data.machine_id:
        existing = crud.get_equipment_by_machine_id(db, data.machine_id)
        if existing:
            raise HTTPException(status_code=409, detail=f"Machine ID '{data.machine_id}' already exists")
    return crud.create_equipment(db, data)


@router.get("/", response_model=PaginatedEquipment)
def list_equipment(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    plant_name: Optional[str] = None,
    machine_type: Optional[str] = None,
    machine_criticality: Optional[str] = None,
    db: Session = Depends(get_db),
):
    total, items = crud.get_equipment_list(db, page, page_size, plant_name, machine_type, machine_criticality)
    return PaginatedEquipment(total=total, page=page, page_size=page_size, items=items)


@router.get("/{equipment_id}", response_model=EquipmentOut)
def get_equipment(equipment_id: UUID, db: Session = Depends(get_db)):
    equipment = crud.get_equipment_by_id(db, equipment_id)
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")
    return equipment


@router.put("/{equipment_id}", response_model=EquipmentOut)
def update_equipment(equipment_id: UUID, data: EquipmentUpdate, db: Session = Depends(get_db)):
    equipment = crud.update_equipment(db, equipment_id, data)
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")
    return equipment


@router.patch("/{equipment_id}", response_model=EquipmentOut)
def patch_equipment(equipment_id: UUID, data: EquipmentUpdate, db: Session = Depends(get_db)):
    equipment = crud.update_equipment(db, equipment_id, data)
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")
    return equipment


@router.delete("/{equipment_id}", status_code=204)
def delete_equipment(equipment_id: UUID, db: Session = Depends(get_db)):
    success = crud.delete_equipment(db, equipment_id)
    if not success:
        raise HTTPException(status_code=404, detail="Equipment not found")


# ── Image Upload ─────────────────────────────────────────────────────────────

@router.post("/{equipment_id}/image", response_model=EquipmentOut)
async def upload_image(equipment_id: UUID, file: UploadFile = File(...), db: Session = Depends(get_db)):
    equipment = crud.get_equipment_by_id(db, equipment_id)
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="File must be an image (JPEG, PNG, WebP, GIF)")
    content = await file.read()
    if len(content) > settings.max_image_size_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"Image exceeds {settings.max_image_size_mb}MB limit")
    os.makedirs(settings.upload_dir, exist_ok=True)
    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "jpg"
    filename = f"{equipment_id}.{ext}"
    filepath = os.path.join(settings.upload_dir, filename)
    with open(filepath, "wb") as f:
        f.write(content)
    return crud.update_image_path(db, equipment_id, filepath)


@router.get("/{equipment_id}/image")
def get_image(equipment_id: UUID, db: Session = Depends(get_db)):
    equipment = crud.get_equipment_by_id(db, equipment_id)
    if not equipment or not equipment.equipment_image_path:
        raise HTTPException(status_code=404, detail="Image not found")
    if not os.path.exists(equipment.equipment_image_path):
        raise HTTPException(status_code=404, detail="Image file not found on disk")
    return FileResponse(equipment.equipment_image_path)


@router.delete("/{equipment_id}/image", status_code=204)
def delete_image(equipment_id: UUID, db: Session = Depends(get_db)):
    equipment = crud.get_equipment_by_id(db, equipment_id)
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")
    if equipment.equipment_image_path and os.path.exists(equipment.equipment_image_path):
        os.remove(equipment.equipment_image_path)
    crud.update_image_path(db, equipment_id, None)


# ── Sensors ──────────────────────────────────────────────────────────────────

@router.get("/{equipment_id}/sensors", response_model=list[SensorConfigOut])
def list_sensors(equipment_id: UUID, db: Session = Depends(get_db)):
    if not crud.get_equipment_by_id(db, equipment_id):
        raise HTTPException(status_code=404, detail="Equipment not found")
    return crud.get_sensors_by_equipment(db, equipment_id)


@router.post("/{equipment_id}/sensors", response_model=SensorConfigOut, status_code=201)
def add_sensor(equipment_id: UUID, data: SensorConfigCreate, db: Session = Depends(get_db)):
    if not crud.get_equipment_by_id(db, equipment_id):
        raise HTTPException(status_code=404, detail="Equipment not found")
    return crud.create_sensor(db, equipment_id, data)


@router.put("/{equipment_id}/sensors/{sensor_id}", response_model=SensorConfigOut)
def update_sensor(equipment_id: UUID, sensor_id: UUID, data: SensorConfigUpdate, db: Session = Depends(get_db)):
    sensor = crud.update_sensor(db, sensor_id, data)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return sensor


@router.delete("/{equipment_id}/sensors/{sensor_id}", status_code=204)
def delete_sensor(equipment_id: UUID, sensor_id: UUID, db: Session = Depends(get_db)):
    if not crud.delete_sensor(db, sensor_id):
        raise HTTPException(status_code=404, detail="Sensor not found")


# ── AI Readiness ──────────────────────────────────────────────────────────────

@router.get("/{equipment_id}/ai-readiness", response_model=AIReadinessOut)
def get_ai_readiness(equipment_id: UUID, db: Session = Depends(get_db)):
    equipment = crud.get_equipment_by_id(db, equipment_id)
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")
    return crud.compute_ai_readiness(equipment)
