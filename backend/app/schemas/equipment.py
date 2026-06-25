from __future__ import annotations
from typing import List, Optional
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


class SensorConfigBase(BaseModel):
    sensor_type: str
    mounting_location: str
    orientation: str
    mounting_method: Optional[str] = None
    sensitivity: Optional[Decimal] = None
    sensitivity_unit: Optional[str] = None
    sampling_rate: Optional[str] = None
    sampling_rate_custom: Optional[int] = None
    frequency_range: Optional[str] = None
    frequency_range_custom_min: Optional[int] = None
    frequency_range_custom_max: Optional[int] = None
    is_active: bool = True
    device_id: Optional[str] = Field(
        default=None,
        max_length=64,
        description="Edge device identifier (MAC-style), e.g. 11:AA:BB:CC:DD:EE",
    )


class SensorConfigCreate(SensorConfigBase):
    pass


class SensorConfigUpdate(BaseModel):
    sensor_type: Optional[str] = None
    mounting_location: Optional[str] = None
    orientation: Optional[str] = None
    mounting_method: Optional[str] = None
    sensitivity: Optional[Decimal] = None
    sensitivity_unit: Optional[str] = None
    sampling_rate: Optional[str] = None
    sampling_rate_custom: Optional[int] = None
    frequency_range: Optional[str] = None
    frequency_range_custom_min: Optional[int] = None
    frequency_range_custom_max: Optional[int] = None
    is_active: Optional[bool] = None
    device_id: Optional[str] = Field(default=None, max_length=64)


class SensorConfigOut(SensorConfigBase):
    id: UUID
    equipment_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


class EquipmentBase(BaseModel):
    # Location & Hierarchy
    plant_name: str = ""
    area: str = ""
    line: str = ""

    # Asset Identification
    machine_name: str = ""
    machine_id: Optional[str] = None
    machine_type: str = ""
    machine_criticality: str = ""
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None

    # Mechanical Details
    rated_power_kw: Optional[Decimal] = None
    rated_rpm: Optional[int] = None
    drive_type: Optional[str] = None
    load_type: Optional[str] = None
    foundation_type: Optional[str] = None
    coupling_details: Optional[str] = None

    # Rotating Components
    bearing_details: Optional[str] = None
    bearing_number_de: Optional[str] = None
    bearing_number_nde: Optional[str] = None
    gearbox_ratio: Optional[Decimal] = None
    gear_teeth: Optional[int] = None
    motor_pole_count: Optional[int] = None
    fan_blades: Optional[int] = None
    pump_vanes: Optional[int] = None
    direction_of_rotation: Optional[str] = None

    # Operating Conditions
    operating_speed_min: Optional[int] = None
    operating_speed_max: Optional[int] = None
    load_range_min: Optional[Decimal] = None
    load_range_max: Optional[Decimal] = None
    normal_operating_load: Optional[Decimal] = None
    process_details: Optional[str] = None
    operating_environment: Optional[List[str]] = None

    # Lubrication & Maintenance
    lubrication_type: Optional[str] = None
    installation_date: Optional[date] = None
    last_maintenance_date: Optional[date] = None
    maintenance_notes: Optional[str] = None

    # AI Readiness
    asset_status: Optional[str] = "Active"
    machine_train_configured: Optional[bool] = False
    bearing_database_mapped: Optional[bool] = False
    operating_mode_configured: Optional[bool] = False

    @field_validator("machine_id", mode="before")
    @classmethod
    def normalize_machine_id(cls, v):
        return None if v == "" else v


class EquipmentCreate(EquipmentBase):
    sensors: Optional[List[SensorConfigCreate]] = []


class EquipmentUpdate(BaseModel):
    plant_name: Optional[str] = None
    area: Optional[str] = None
    line: Optional[str] = None
    machine_name: Optional[str] = None
    machine_id: Optional[str] = None
    machine_type: Optional[str] = None
    machine_criticality: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    rated_power_kw: Optional[Decimal] = None
    rated_rpm: Optional[int] = None
    drive_type: Optional[str] = None
    load_type: Optional[str] = None
    foundation_type: Optional[str] = None
    coupling_details: Optional[str] = None
    bearing_details: Optional[str] = None
    bearing_number_de: Optional[str] = None
    bearing_number_nde: Optional[str] = None
    gearbox_ratio: Optional[Decimal] = None
    gear_teeth: Optional[int] = None
    motor_pole_count: Optional[int] = None
    fan_blades: Optional[int] = None
    pump_vanes: Optional[int] = None
    direction_of_rotation: Optional[str] = None
    operating_speed_min: Optional[int] = None
    operating_speed_max: Optional[int] = None
    load_range_min: Optional[Decimal] = None
    load_range_max: Optional[Decimal] = None
    normal_operating_load: Optional[Decimal] = None
    process_details: Optional[str] = None
    operating_environment: Optional[List[str]] = None
    lubrication_type: Optional[str] = None
    installation_date: Optional[date] = None
    last_maintenance_date: Optional[date] = None
    maintenance_notes: Optional[str] = None
    asset_status: Optional[str] = None
    machine_train_configured: Optional[bool] = None
    bearing_database_mapped: Optional[bool] = None
    operating_mode_configured: Optional[bool] = None


class EquipmentOut(EquipmentBase):
    id: UUID
    equipment_image_path: Optional[str] = None
    sensors: List[SensorConfigOut] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EquipmentListItem(BaseModel):
    id: UUID
    plant_name: str
    area: str
    line: str
    machine_name: str
    machine_id: Optional[str] = None
    machine_type: str
    machine_criticality: str
    manufacturer: Optional[str] = None
    asset_status: Optional[str] = None
    equipment_image_path: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AIReadinessOut(BaseModel):
    equipment_id: UUID
    score_percent: int
    machine_train_configured: bool
    asset_status_set: bool
    sensor_coverage: bool
    bearing_database_mapped: bool
    operating_mode_configured: bool


class PaginatedEquipment(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[EquipmentListItem]
