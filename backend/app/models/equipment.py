import uuid
from datetime import datetime, date
from sqlalchemy import (
    Column, String, Integer, Numeric, Boolean, Text,
    Date, DateTime, ForeignKey, ARRAY
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class Equipment(Base):
    __tablename__ = "equipment_masters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Location & Hierarchy
    # plant_id/area_id/line_id are the source of truth; the three text columns
    # are denormalised copies kept in sync on write so existing filters,
    # lookups and dashboard grouping keep working without a join.
    plant_id = Column(UUID(as_uuid=True), ForeignKey("plants.id", ondelete="RESTRICT"), nullable=True, index=True)
    area_id = Column(UUID(as_uuid=True), ForeignKey("areas.id", ondelete="RESTRICT"), nullable=True, index=True)
    line_id = Column(UUID(as_uuid=True), ForeignKey("lines.id", ondelete="RESTRICT"), nullable=True, index=True)

    plant_name = Column(String(255), nullable=False)
    area = Column(String(255), nullable=False)
    line = Column(String(255), nullable=False)

    # Asset Identification
    machine_name = Column(String(255), nullable=False)
    machine_id = Column(String(100), nullable=True, unique=True, index=True)
    machine_type = Column(String(50), nullable=False)
    machine_criticality = Column(String(20), nullable=False)
    manufacturer = Column(String(255), nullable=True)
    model = Column(String(255), nullable=True)
    serial_number = Column(String(100), nullable=True)

    # Mechanical Details
    rated_power_kw = Column(Numeric(10, 2), nullable=True)
    rated_rpm = Column(Integer, nullable=True)
    drive_type = Column(String(50), nullable=True)
    load_type = Column(String(50), nullable=True)
    foundation_type = Column(String(50), nullable=True)
    coupling_details = Column(String(50), nullable=True)

    # Rotating Components
    bearing_details = Column(Text, nullable=True)
    bearing_number_de = Column(String(100), nullable=True)
    bearing_number_nde = Column(String(100), nullable=True)
    # Link to the bearing catalogue, by its own Bearing ID. Only the id is kept:
    # copying the seven catalogue fields onto every machine would go stale the
    # moment the catalogue is corrected, and the numbers are one join away.
    # Deliberately not a foreign key — the catalogue is optional reference data
    # that a deployment may not have loaded, and an equipment record must stay
    # saveable either way.
    bearing_de_catalog_id = Column(Integer, nullable=True)
    bearing_nde_catalog_id = Column(Integer, nullable=True)
    gearbox_ratio = Column(Numeric(8, 3), nullable=True)
    gear_teeth = Column(Integer, nullable=True)
    motor_pole_count = Column(Integer, nullable=True)
    fan_blades = Column(Integer, nullable=True)
    pump_vanes = Column(Integer, nullable=True)
    direction_of_rotation = Column(String(30), nullable=True)

    # Operating Conditions
    operating_speed_min = Column(Integer, nullable=True)
    operating_speed_max = Column(Integer, nullable=True)
    load_range_min = Column(Numeric(5, 2), nullable=True)
    load_range_max = Column(Numeric(5, 2), nullable=True)
    normal_operating_load = Column(Numeric(5, 2), nullable=True)
    process_details = Column(Text, nullable=True)
    operating_environment = Column(ARRAY(String), nullable=True)

    # Lubrication & Maintenance
    lubrication_type = Column(String(50), nullable=True)
    installation_date = Column(Date, nullable=True)
    last_maintenance_date = Column(Date, nullable=True)
    maintenance_notes = Column(Text, nullable=True)

    # Equipment Image
    equipment_image_path = Column(String(500), nullable=True)

    # AI Readiness
    asset_status = Column(String(30), nullable=True, default="Active")
    machine_train_configured = Column(Boolean, default=False)
    bearing_database_mapped = Column(Boolean, default=False)
    operating_mode_configured = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    sensors = relationship("SensorConfiguration", back_populates="equipment", cascade="all, delete-orphan")
    plant = relationship("Plant")
    area_ref = relationship("Area")
    line_ref = relationship("Line")
