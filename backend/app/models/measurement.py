import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Numeric, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.database import Base


class PlotConfiguration(Base):
    """Per-sensor plot / data-fetch configuration (configure API)."""
    __tablename__ = "plot_configurations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sensor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sensor_configurations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    channel_count = Column(Integer, nullable=False, default=1)
    active_channel = Column(Integer, nullable=False, default=0)
    sampling_rate_hz = Column(Numeric(12, 4), nullable=False, default=25600)
    fft_lines = Column(Integer, nullable=False, default=1600)
    frequency_max_hz = Column(Numeric(12, 4), nullable=True)
    data_type = Column(String(30), nullable=False, default="acceleration")
    enabled_plots = Column(JSONB, nullable=False, default=list)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sensor = relationship("SensorConfiguration", backref="plot_configuration")


class SensorDataUpload(Base):
    """Uploaded sensor PDF and parsed measurement metadata."""
    __tablename__ = "sensor_data_uploads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sensor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sensor_configurations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    channel_count = Column(Integer, nullable=False)
    pdf_path = Column(String(500), nullable=False)
    parsed_data_path = Column(String(500), nullable=True)
    sample_count = Column(Integer, nullable=True)
    parse_status = Column(String(20), nullable=False, default="pending")
    parse_error = Column(Text, nullable=True)
    plots_status = Column(String(20), nullable=False, default="pending")
    plots_error = Column(Text, nullable=True)
    plots_computed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    parsed_at = Column(DateTime, nullable=True)

    sensor = relationship("SensorConfiguration", backref="data_uploads")
    plot_results = relationship("PlotResult", back_populates="upload", cascade="all, delete-orphan")


class PlotResult(Base):
    """Stored computed plot series (x/y arrays) per upload, channel, and plot type."""
    __tablename__ = "plot_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    upload_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sensor_data_uploads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sensor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sensor_configurations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    plot_type = Column(String(40), nullable=False)
    channel = Column(Integer, nullable=False)
    title = Column(String(120), nullable=False)
    x_label = Column(String(80), nullable=False)
    y_label = Column(String(80), nullable=False)
    x_data = Column(JSONB, nullable=False)
    y_data = Column(JSONB, nullable=False)
    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)
    point_count = Column(Integer, nullable=False)
    sampling_rate_hz = Column(Numeric(12, 4), nullable=False)
    fft_lines = Column(Integer, nullable=True)
    frequency_max_hz = Column(Numeric(12, 4), nullable=True)
    config_fingerprint = Column(String(64), nullable=False)
    computed_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20), nullable=False, default="ready")

    upload = relationship("SensorDataUpload", back_populates="plot_results")
