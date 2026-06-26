import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Numeric, DateTime, ForeignKey, Text, Boolean, LargeBinary
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
    features_status = Column(String(20), nullable=False, default="pending")
    features_error = Column(Text, nullable=True)
    features_computed_at = Column(DateTime, nullable=True)
    original_filename = Column(String(255), nullable=True)
    source = Column(String(20), nullable=False, default="manual")

    created_at = Column(DateTime, default=datetime.utcnow)
    parsed_at = Column(DateTime, nullable=True)

    sensor = relationship("SensorConfiguration", backref="data_uploads")
    plot_results = relationship("PlotResult", back_populates="upload", cascade="all, delete-orphan")
    channel_features = relationship(
        "MeasurementChannelFeature", back_populates="upload", cascade="all, delete-orphan"
    )
    channel_feature_trends = relationship(
        "MeasurementChannelFeatureTrend", back_populates="upload", cascade="all, delete-orphan"
    )


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


class MeasurementUploadData(Base):
    """Full uploaded file bytes + parsed channel data stored in PostgreSQL."""
    __tablename__ = "measurement_upload_data"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    upload_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sensor_data_uploads.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    sensor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sensor_configurations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_filename = Column(String(255), nullable=False)
    file_format = Column(String(10), nullable=False)
    file_content = Column(LargeBinary, nullable=False)
    parsed_data = Column(JSONB, nullable=False)
    channel_count = Column(Integer, nullable=False)
    sample_count = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    upload = relationship("SensorDataUpload", backref="upload_data", uselist=False)


class SensorBaseline(Base):
    """Historical baseline records — all rows kept (append-only) for RAG / learning."""
    __tablename__ = "sensor_baselines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sensor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sensor_configurations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_upload_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sensor_data_uploads.id", ondelete="SET NULL"),
        nullable=True,
    )
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    labels = Column(JSONB, nullable=False, default=list)
    original_filename = Column(String(255), nullable=False)
    file_format = Column(String(10), nullable=False)
    file_content = Column(LargeBinary, nullable=False)
    parsed_data = Column(JSONB, nullable=False)
    channel_count = Column(Integer, nullable=False)
    sample_count = Column(Integer, nullable=False)
    sampling_rate_hz = Column(Numeric(12, 4), nullable=False)
    is_primary = Column(Boolean, nullable=False, default=False)
    captured_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    plot_results = relationship("BaselinePlotResult", back_populates="baseline", cascade="all, delete-orphan")
    channel_features = relationship(
        "BaselineChannelFeature", back_populates="baseline", cascade="all, delete-orphan"
    )


class FeatureDefinition(Base):
    __tablename__ = "feature_definitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(40), nullable=False, unique=True)
    name = Column(String(120), nullable=False)
    unit = Column(String(30), nullable=False)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)


class FeatureThresholdRule(Base):
    __tablename__ = "feature_threshold_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feature_code = Column(String(40), ForeignKey("feature_definitions.code"), nullable=False)
    rule_type = Column(String(30), nullable=False)
    machine_type = Column(String(80), nullable=True)
    normal_max = Column(Numeric(18, 8), nullable=True)
    warning_max = Column(Numeric(18, 8), nullable=True)
    normal_min = Column(Numeric(18, 8), nullable=True)
    warning_min = Column(Numeric(18, 8), nullable=True)
    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)
    is_active = Column(Boolean, nullable=False, default=True)


class MeasurementChannelFeature(Base):
    __tablename__ = "measurement_channel_features"

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
    )
    channel = Column(Integer, nullable=False)
    feature_code = Column(String(40), ForeignKey("feature_definitions.code"), nullable=False)
    value = Column(Numeric(18, 8), nullable=False)
    unit = Column(String(30), nullable=False)
    status = Column(String(20), nullable=False)
    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)
    computed_at = Column(DateTime, default=datetime.utcnow)

    upload = relationship("SensorDataUpload", back_populates="channel_features")


class MeasurementChannelFeatureTrend(Base):
    __tablename__ = "measurement_channel_feature_trends"

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
    )
    channel = Column(Integer, nullable=False)
    feature_code = Column(String(40), ForeignKey("feature_definitions.code"), nullable=False)
    segment_index = Column(Integer, nullable=False)
    time_s = Column(Numeric(18, 8), nullable=False)
    value = Column(Numeric(18, 8), nullable=False)
    computed_at = Column(DateTime, default=datetime.utcnow)

    upload = relationship("SensorDataUpload", back_populates="channel_feature_trends")


class BaselineChannelFeature(Base):
    __tablename__ = "baseline_channel_features"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    baseline_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sensor_baselines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sensor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sensor_configurations.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel = Column(Integer, nullable=False)
    feature_code = Column(String(40), ForeignKey("feature_definitions.code"), nullable=False)
    value = Column(Numeric(18, 8), nullable=False)
    unit = Column(String(30), nullable=False)
    status = Column(String(20), nullable=False, default="normal")
    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)
    computed_at = Column(DateTime, default=datetime.utcnow)

    baseline = relationship("SensorBaseline", back_populates="channel_features")


class BaselinePlotResult(Base):
    """Stored computed plot series for a baseline record."""
    __tablename__ = "baseline_plot_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    baseline_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sensor_baselines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sensor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sensor_configurations.id", ondelete="CASCADE"),
        nullable=False,
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

    baseline = relationship("SensorBaseline", back_populates="plot_results")
