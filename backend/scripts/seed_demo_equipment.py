"""Add one machine per Machine Type, so every Digital Twin model is reachable.

Step 1 offers thirteen machine types, and they collapse onto seven 3D model
families. With only a Pump and a Blower on the platform, five of those families
have nothing to open them with — the models exist and nothing reaches them.

This adds the eleven missing types with plausible details and two sensors each,
so the twin has bearings and mounting points to draw rather than a bare model.
They land in the same plant, area and line as the existing two, so the list
stays one readable group.

Idempotent: a machine whose `machine_id` is already present is skipped, so
re-running adds nothing and changes nothing. Goes through `EquipmentCreate` and
`crud.create_equipment` — the same validation and the same code path as
POST /api/v1/equipment, just without the HTTP hop.

Run:  python backend/scripts/seed_demo_equipment.py
"""
from __future__ import annotations

import os
import sys

# Importable from anywhere, not only from inside backend/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Same plant/area/line as the machines already on the platform.
PLANT, AREA, LINE = "pune", "warje", "atul nagar"
MAKER = "sensovibe"


def sensor(kind: str, location: str, orientation: str) -> dict:
    return {
        "sensor_type": kind,
        "mounting_location": location,
        "orientation": orientation,
        "mounting_method": "Stud Mounted",
        "sampling_rate": "2048 Hz",
        "frequency_range": "0-1000 Hz",
    }


ACC = "IEPE Accelerometer"

#: machine_id, name, type, criticality, kW, rpm, model, sensors
MACHINES = [
    (
        "MTR-102", "Boiler Feed Motor", "Motor", "Critical", "75.0", 2970,
        "Siemens 1LE1",
        [sensor(ACC, "Motor DE", "Horizontal"), sensor(ACC, "Motor NDE", "Vertical")],
    ),
    (
        "FAN-101", "Cooling Tower Fan", "Fan", "High", "45.0", 1480,
        "Kruger BSB-900",
        [sensor(ACC, "Bearing Housing DE", "Horizontal"), sensor(ACC, "Fan Housing", "Vertical")],
    ),
    (
        "CMP-103", "Instrument Air Compressor", "Compressor", "High", "110.0", 1480,
        "Atlas Copco GA110",
        [
            sensor(ACC, "Compressor Housing", "Horizontal"),
            sensor(ACC, "Bearing Housing DE", "Axial"),
        ],
    ),
    (
        "GBX-104", "Ball Mill Gearbox", "Gearbox", "Critical", "250.0", 990,
        "Flender H3SH",
        [sensor(ACC, "Gearbox Input", "Horizontal"), sensor(ACC, "Gearbox Output", "Vertical")],
    ),
    (
        "TRB-105", "Steam Turbine", "Turbine", "Critical", "1500.0", 3000,
        "Siemens SST-300",
        [
            sensor(ACC, "Bearing Housing DE", "Horizontal"),
            sensor(ACC, "Bearing Housing NDE", "Vertical"),
        ],
    ),
    (
        "GEN-106", "Standby Generator", "Generator", "High", "500.0", 1500,
        "Stamford HCI544",
        [sensor(ACC, "Motor DE", "Horizontal"), sensor(ACC, "Motor NDE", "Horizontal")],
    ),
    (
        "DG-107", "Emergency DG Set", "DG Set", "Medium", "320.0", 1500,
        "Cummins C320D5",
        [sensor(ACC, "Motor DE", "Horizontal"), sensor("Thermocouple", "Foundation", "Vertical")],
    ),
    (
        "CNV-108", "Clinker Belt Conveyor", "Conveyor", "Medium", "22.0", 960,
        "Rulmeca MDR",
        [sensor(ACC, "Bearing Housing DE", "Horizontal"), sensor(ACC, "Foundation", "Vertical")],
    ),
    (
        "CRS-109", "Primary Jaw Crusher", "Crusher", "High", "160.0", 740,
        "Metso C120",
        [sensor(ACC, "Bearing Housing DE", "Horizontal"), sensor(ACC, "Foundation", "Vertical")],
    ),
    (
        "MIX-110", "Slurry Mixer", "Mixer", "Low", "30.0", 1450,
        "Ekato Unimix",
        [sensor(ACC, "Bearing Housing DE", "Horizontal"), sensor(ACC, "Foundation", "Vertical")],
    ),
    (
        "AGT-111", "Reactor Agitator", "Agitator", "Medium", "18.5", 960,
        "Ekato Paravisc",
        [sensor(ACC, "Bearing Housing DE", "Vertical"), sensor(ACC, "Foundation", "Horizontal")],
    ),
    # The two machine types added with the GLB library. Without one of each,
    # spindle.glb and wind-turbine-drivetrain.glb have nothing to open them.
    (
        "SPN-112", "CNC Grinding Spindle", "Spindle", "High", "15.0", 18000,
        "GMN HCS 170",
        [
            sensor(ACC, "Bearing Housing DE", "Horizontal"),
            sensor(ACC, "Bearing Housing NDE", "Vertical"),
        ],
    ),
    (
        "WTG-113", "Wind Turbine Drivetrain", "Wind Turbine", "Critical", "2500.0", 1500,
        "Vestas V90 drivetrain",
        [
            sensor(ACC, "Gearbox Input", "Horizontal"),
            sensor(ACC, "Motor DE", "Axial"),
            sensor(ACC, "Foundation", "Vertical"),
        ],
    ),
]


def main() -> None:
    if not os.environ.get("DATABASE_URL"):
        sys.exit("DATABASE_URL is not set — refusing to guess which database to write to.")

    from app.crud import equipment as crud
    from app.database import SessionLocal
    from app.schemas.equipment import EquipmentCreate

    db = SessionLocal()
    added, skipped = [], []
    try:
        for machine_id, name, kind, criticality, kw, rpm, model, sensors in MACHINES:
            if crud.get_equipment_by_machine_id(db, machine_id):
                skipped.append(machine_id)
                continue

            crud.create_equipment(
                db,
                EquipmentCreate(
                    plant_name=PLANT,
                    area=AREA,
                    line=LINE,
                    machine_name=name,
                    machine_id=machine_id,
                    machine_type=kind,
                    machine_criticality=criticality,
                    manufacturer=MAKER,
                    model=model,
                    rated_power_kw=kw,
                    rated_rpm=rpm,
                    operating_environment=["Indoor"],
                    sensors=sensors,
                ),
            )
            added.append(f"{machine_id}  {kind:<12} {name}")
    finally:
        db.close()

    for line in added:
        print(f"  + {line}")
    if skipped:
        print(f"\n  {len(skipped)} already present, left alone: {', '.join(skipped)}")
    print(f"\n{len(added)} machines added.")


if __name__ == "__main__":
    main()
