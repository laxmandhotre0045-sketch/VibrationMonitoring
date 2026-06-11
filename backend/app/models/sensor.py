import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Numeric, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class SensorConfiguration(Base):
    __tablename__ = "sensor_configurations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    equipment_id = Column(UUID(as_uuid=True), ForeignKey("equipment_masters.id", ondelete="CASCADE"), nullable=False)

    sensor_type = Column(String(50), nullable=False)
    mounting_location = Column(String(100), nullable=False)
    orientation = Column(String(30), nullable=False)
    mounting_method = Column(String(50), nullable=True)
    sensitivity = Column(Numeric(10, 4), nullable=True)
    sensitivity_unit = Column(String(20), nullable=True)
    sampling_rate = Column(String(20), nullable=True)
    sampling_rate_custom = Column(Integer, nullable=True)
    frequency_range = Column(String(20), nullable=True)
    frequency_range_custom_min = Column(Integer, nullable=True)
    frequency_range_custom_max = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True)
    device_id = Column(String(64), nullable=True, unique=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    equipment = relationship("Equipment", back_populates="sensors")
