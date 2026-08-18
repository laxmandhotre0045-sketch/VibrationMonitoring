from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


def _require_text(value: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError("must not be blank")
    return cleaned


class PlantCreate(BaseModel):
    name: str = Field(max_length=255)
    code: Optional[str] = Field(default=None, max_length=50)
    location: Optional[str] = Field(default=None, max_length=255)
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        return _require_text(value)

    @field_validator("code", "location")
    @classmethod
    def _clean_optional(cls, value: Optional[str]) -> Optional[str]:
        cleaned = (value or "").strip()
        return cleaned or None


class PlantUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    code: Optional[str] = Field(default=None, max_length=50)
    location: Optional[str] = Field(default=None, max_length=255)
    is_active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: Optional[str]) -> Optional[str]:
        return _require_text(value) if value is not None else None


class AreaCreate(BaseModel):
    name: str = Field(max_length=255)
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        return _require_text(value)


class AreaUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    is_active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: Optional[str]) -> Optional[str]:
        return _require_text(value) if value is not None else None


class LineCreate(AreaCreate):
    pass


class LineUpdate(AreaUpdate):
    pass


class LineOut(BaseModel):
    id: UUID
    area_id: UUID
    name: str
    is_active: bool
    equipment_count: int = 0

    class Config:
        from_attributes = True


class AreaOut(BaseModel):
    id: UUID
    plant_id: UUID
    name: str
    is_active: bool
    equipment_count: int = 0
    lines: List[LineOut] = []

    class Config:
        from_attributes = True


class PlantOut(BaseModel):
    id: UUID
    name: str
    code: Optional[str] = None
    location: Optional[str] = None
    is_active: bool
    area_count: int = 0
    equipment_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class PlantDetailOut(PlantOut):
    areas: List[AreaOut] = []
