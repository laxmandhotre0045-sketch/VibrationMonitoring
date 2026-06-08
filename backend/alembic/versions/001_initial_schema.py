"""initial schema

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "equipment_masters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        # Location
        sa.Column("plant_name", sa.String(255), nullable=False),
        sa.Column("area", sa.String(255), nullable=False),
        sa.Column("line", sa.String(255), nullable=False),
        # Asset Identification
        sa.Column("machine_name", sa.String(255), nullable=False),
        sa.Column("machine_id", sa.String(100), nullable=True),
        sa.Column("machine_type", sa.String(50), nullable=False),
        sa.Column("machine_criticality", sa.String(20), nullable=False),
        sa.Column("manufacturer", sa.String(255), nullable=True),
        sa.Column("model", sa.String(255), nullable=True),
        sa.Column("serial_number", sa.String(100), nullable=True),
        # Mechanical Details
        sa.Column("rated_power_kw", sa.Numeric(10, 2), nullable=True),
        sa.Column("rated_rpm", sa.Integer, nullable=True),
        sa.Column("drive_type", sa.String(50), nullable=True),
        sa.Column("load_type", sa.String(50), nullable=True),
        sa.Column("foundation_type", sa.String(50), nullable=True),
        sa.Column("coupling_details", sa.String(50), nullable=True),
        # Rotating Components
        sa.Column("bearing_details", sa.Text, nullable=True),
        sa.Column("bearing_number_de", sa.String(100), nullable=True),
        sa.Column("bearing_number_nde", sa.String(100), nullable=True),
        sa.Column("gearbox_ratio", sa.Numeric(8, 3), nullable=True),
        sa.Column("gear_teeth", sa.Integer, nullable=True),
        sa.Column("motor_pole_count", sa.Integer, nullable=True),
        sa.Column("fan_blades", sa.Integer, nullable=True),
        sa.Column("pump_vanes", sa.Integer, nullable=True),
        sa.Column("direction_of_rotation", sa.String(30), nullable=True),
        # Operating Conditions
        sa.Column("operating_speed_min", sa.Integer, nullable=True),
        sa.Column("operating_speed_max", sa.Integer, nullable=True),
        sa.Column("load_range_min", sa.Numeric(5, 2), nullable=True),
        sa.Column("load_range_max", sa.Numeric(5, 2), nullable=True),
        sa.Column("normal_operating_load", sa.Numeric(5, 2), nullable=True),
        sa.Column("process_details", sa.Text, nullable=True),
        sa.Column("operating_environment", postgresql.ARRAY(sa.String), nullable=True),
        # Lubrication & Maintenance
        sa.Column("lubrication_type", sa.String(50), nullable=True),
        sa.Column("installation_date", sa.Date, nullable=True),
        sa.Column("last_maintenance_date", sa.Date, nullable=True),
        sa.Column("maintenance_notes", sa.Text, nullable=True),
        # Image
        sa.Column("equipment_image_path", sa.String(500), nullable=True),
        # AI Readiness
        sa.Column("asset_status", sa.String(30), nullable=True, server_default="Active"),
        sa.Column("machine_train_configured", sa.Boolean, server_default="false"),
        sa.Column("bearing_database_mapped", sa.Boolean, server_default="false"),
        sa.Column("operating_mode_configured", sa.Boolean, server_default="false"),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_unique_constraint("uq_equipment_machine_id", "equipment_masters", ["machine_id"])
    op.create_index("ix_equipment_plant_name", "equipment_masters", ["plant_name"])
    op.create_index("ix_equipment_machine_type", "equipment_masters", ["machine_type"])

    op.create_table(
        "sensor_configurations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("equipment_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("equipment_masters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sensor_type", sa.String(50), nullable=False),
        sa.Column("mounting_location", sa.String(100), nullable=False),
        sa.Column("orientation", sa.String(30), nullable=False),
        sa.Column("mounting_method", sa.String(50), nullable=True),
        sa.Column("sensitivity", sa.Numeric(10, 4), nullable=True),
        sa.Column("sensitivity_unit", sa.String(20), nullable=True),
        sa.Column("sampling_rate", sa.String(20), nullable=True),
        sa.Column("sampling_rate_custom", sa.Integer, nullable=True),
        sa.Column("frequency_range", sa.String(20), nullable=True),
        sa.Column("frequency_range_custom_min", sa.Integer, nullable=True),
        sa.Column("frequency_range_custom_max", sa.Integer, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_sensor_equipment_id", "sensor_configurations", ["equipment_id"])


def downgrade() -> None:
    op.drop_table("sensor_configurations")
    op.drop_table("equipment_masters")
