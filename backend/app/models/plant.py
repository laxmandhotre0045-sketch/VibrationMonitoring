import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Boolean, DateTime, ForeignKey, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class Plant(Base):
    """Top of the location hierarchy: plants -> areas -> lines -> equipment."""

    __tablename__ = "plants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True, index=True)
    code = Column(String(50), nullable=True, unique=True)
    location = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    areas = relationship(
        "Area",
        back_populates="plant",
        cascade="all, delete-orphan",
        order_by="Area.name",
    )


class Area(Base):
    __tablename__ = "areas"
    __table_args__ = (UniqueConstraint("plant_id", "name", name="uq_areas_plant_name"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plant_id = Column(
        UUID(as_uuid=True), ForeignKey("plants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    plant = relationship("Plant", back_populates="areas")
    lines = relationship(
        "Line",
        back_populates="area",
        cascade="all, delete-orphan",
        order_by="Line.name",
    )


class Line(Base):
    __tablename__ = "lines"
    __table_args__ = (UniqueConstraint("area_id", "name", name="uq_lines_area_name"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    area_id = Column(
        UUID(as_uuid=True), ForeignKey("areas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    area = relationship("Area", back_populates="lines")
