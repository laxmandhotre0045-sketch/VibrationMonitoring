"""plants / areas / lines hierarchy, with equipment FKs backfilled from the free text

Revision ID: 012
Revises: 011
Create Date: 2026-08-18 12:00:00.000000
"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _norm(value) -> str:
    return (value or "").strip()


def _backfill(conn) -> None:
    """Create one plant/area/line per distinct free-text value, then point every
    equipment row at them. Matching is case-insensitive, so "Plant A" and
    "plant a" collapse into a single plant; the first spelling seen wins."""
    rows = conn.execute(
        sa.text("SELECT id, plant_name, area, line FROM equipment_masters")
    ).fetchall()
    if not rows:
        return

    # Each map holds (id, canonical_name) so the text columns below can be
    # rewritten to the registry's spelling rather than this row's spelling.
    plants: dict[str, tuple] = {}
    areas: dict[tuple, tuple] = {}
    lines: dict[tuple, tuple] = {}

    for eq_id, plant_name, area, line in rows:
        p_name, a_name, l_name = _norm(plant_name), _norm(area), _norm(line)
        if not p_name or not a_name or not l_name:
            # These are NOT NULL columns, so this should not happen. Skip the
            # row rather than invent a placeholder plant for it.
            continue

        p_key = p_name.lower()
        if p_key not in plants:
            new_id = uuid.uuid4()
            conn.execute(
                sa.text("INSERT INTO plants (id, name, is_active) VALUES (:id, :name, true)"),
                {"id": new_id, "name": p_name},
            )
            plants[p_key] = (new_id, p_name)
        plant_id, p_name = plants[p_key]

        a_key = (plant_id, a_name.lower())
        if a_key not in areas:
            new_id = uuid.uuid4()
            conn.execute(
                sa.text(
                    "INSERT INTO areas (id, plant_id, name, is_active) "
                    "VALUES (:id, :plant_id, :name, true)"
                ),
                {"id": new_id, "plant_id": plant_id, "name": a_name},
            )
            areas[a_key] = (new_id, a_name)
        area_id, a_name = areas[a_key]

        l_key = (area_id, l_name.lower())
        if l_key not in lines:
            new_id = uuid.uuid4()
            conn.execute(
                sa.text(
                    "INSERT INTO lines (id, area_id, name, is_active) "
                    "VALUES (:id, :area_id, :name, true)"
                ),
                {"id": new_id, "area_id": area_id, "name": l_name},
            )
            lines[l_key] = (new_id, l_name)
        line_id, l_name = lines[l_key]

        conn.execute(
            sa.text(
                "UPDATE equipment_masters "
                "SET plant_id = :plant_id, area_id = :area_id, line_id = :line_id, "
                "    plant_name = :plant_name, area = :area, line = :line "
                "WHERE id = :eq_id"
            ),
            {
                "plant_id": plant_id,
                "area_id": area_id,
                "line_id": line_id,
                # Rewrite the text columns to the canonical spelling so the
                # denormalised copies agree with the registry from day one.
                "plant_name": p_name,
                "area": a_name,
                "line": l_name,
                "eq_id": eq_id,
            },
        )


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = set(inspector.get_table_names())

    if "plants" not in existing:
        op.create_table(
            "plants",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("code", sa.String(50), nullable=True),
            sa.Column("location", sa.String(255), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint("name", name="uq_plants_name"),
            sa.UniqueConstraint("code", name="uq_plants_code"),
        )
        op.create_index("ix_plants_name", "plants", ["name"])

    if "areas" not in existing:
        op.create_table(
            "areas",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "plant_id",
                UUID(as_uuid=True),
                sa.ForeignKey("plants.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint("plant_id", "name", name="uq_areas_plant_name"),
        )
        op.create_index("ix_areas_plant_id", "areas", ["plant_id"])

    if "lines" not in existing:
        op.create_table(
            "lines",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "area_id",
                UUID(as_uuid=True),
                sa.ForeignKey("areas.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint("area_id", "name", name="uq_lines_area_name"),
        )
        op.create_index("ix_lines_area_id", "lines", ["area_id"])

    equipment_columns = {c["name"] for c in inspector.get_columns("equipment_masters")}

    if "plant_id" not in equipment_columns:
        op.add_column(
            "equipment_masters", sa.Column("plant_id", UUID(as_uuid=True), nullable=True)
        )
        op.create_foreign_key(
            "fk_equipment_plant_id",
            "equipment_masters",
            "plants",
            ["plant_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index("ix_equipment_plant_id", "equipment_masters", ["plant_id"])

    if "area_id" not in equipment_columns:
        op.add_column(
            "equipment_masters", sa.Column("area_id", UUID(as_uuid=True), nullable=True)
        )
        op.create_foreign_key(
            "fk_equipment_area_id",
            "equipment_masters",
            "areas",
            ["area_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index("ix_equipment_area_id", "equipment_masters", ["area_id"])

    if "line_id" not in equipment_columns:
        op.add_column(
            "equipment_masters", sa.Column("line_id", UUID(as_uuid=True), nullable=True)
        )
        op.create_foreign_key(
            "fk_equipment_line_id",
            "equipment_masters",
            "lines",
            ["line_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index("ix_equipment_line_id", "equipment_masters", ["line_id"])

    _backfill(conn)


def downgrade() -> None:
    for index in ("ix_equipment_line_id", "ix_equipment_area_id", "ix_equipment_plant_id"):
        op.drop_index(index, table_name="equipment_masters")
    for constraint in ("fk_equipment_line_id", "fk_equipment_area_id", "fk_equipment_plant_id"):
        op.drop_constraint(constraint, "equipment_masters", type_="foreignkey")
    for column in ("line_id", "area_id", "plant_id"):
        op.drop_column("equipment_masters", column)

    op.drop_table("lines")
    op.drop_table("areas")
    op.drop_table("plants")
