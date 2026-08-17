from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.equipment import Equipment

router = APIRouter(
    prefix="/api/v1/lookups",
    tags=["Lookups"],
    dependencies=[Depends(get_current_user)],
)

LOOKUPS = {
    "machine-types": [
        "Motor", "Pump", "Fan", "Blower", "Compressor", "Gearbox",
        "Turbine", "Generator", "DG Set", "Conveyor", "Crusher", "Mixer", "Agitator",
    ],
    "machine-criticality": ["Low", "Medium", "High", "Critical"],
    "drive-types": [
        "Direct Drive", "Belt Drive", "Gear Drive", "Chain Drive", "VFD Drive", "Hydraulic Drive",
    ],
    "load-types": [
        "Constant Load", "Variable Load", "Intermittent Load", "Cyclic Load", "Shock Load",
    ],
    "foundation-types": [
        "Concrete Foundation", "Steel Structure", "Skid Mounted", "Base Frame", "Suspended Structure",
    ],
    "coupling-types": [
        "Flexible", "Grid", "Gear", "Jaw", "Disc", "Tyre", "Chain", "Fluid", "Direct",
    ],
    "motor-pole-counts": [2, 4, 6, 8, 10, 12],
    "direction-of-rotation": ["Clockwise", "Counter-Clockwise", "Bidirectional"],
    "operating-environments": [
        "Indoor", "Outdoor", "Dusty", "Wet Area", "High Temperature", "Low Temperature",
        "Corrosive Environment", "Chemical Area", "Hazardous Area", "Marine Environment",
        "Mining Environment", "Clean Room", "Food Grade Area",
    ],
    "lubrication-types": [
        "Grease", "Oil Bath", "Oil Mist", "Forced Oil", "Splash Lubrication", "Automatic Lubrication",
    ],
    "sensor-types": [
        "IEPE Accelerometer", "MEMS Accelerometer", "Velocity Sensor", "Displacement Probe",
        "Eddy Current Probe", "Ultrasound Sensor", "Temperature Sensor", "RTD", "Thermocouple",
        "Pressure Sensor", "Current Sensor", "Flow Sensor", "Tachometer", "RPM Sensor",
    ],
    "mounting-locations": [
        "Bearing Housing DE", "Bearing Housing NDE", "Motor DE", "Motor NDE",
        "Gearbox Input", "Gearbox Output", "Pump Casing", "Fan Housing",
        "Compressor Housing", "Foundation", "Custom",
    ],
    "sensor-orientations": ["Horizontal", "Vertical", "Axial", "Radial", "Tangential"],
    "mounting-methods": [
        "Stud Mounted", "Magnetic Base", "Adhesive Mounted", "Handheld",
        "Threaded Mount", "Embedded", "Bracket Mounted", "Probe Holder", "Custom",
    ],
    "sensitivity-units": ["mV/g", "mV/mm/s", "mV/µm", "mA", "V"],
    "sampling-rates": [
        "512 Hz", "1024 Hz", "2048 Hz", "4096 Hz",
        "8192 Hz", "16384 Hz", "32768 Hz", "65536 Hz", "Custom",
    ],
    "frequency-ranges": [
        "0-500 Hz", "0-1000 Hz", "0-2000 Hz", "0-5000 Hz",
        "0-10000 Hz", "0-20000 Hz", "Custom",
    ],
    "asset-status": ["Active", "Inactive", "Under Maintenance", "Decommissioned"],
}


def plant_names(db: Session) -> list[str]:
    """Distinct plant names actually present in the equipment master."""
    rows = (
        db.query(Equipment.plant_name)
        .distinct()
        .order_by(Equipment.plant_name.asc())
        .all()
    )
    return [row[0] for row in rows if (row[0] or "").strip()]


@router.get("/")
def get_all_lookups(db: Session = Depends(get_db)):
    return {**LOOKUPS, "plants": plant_names(db)}


# Declared before /{lookup_name} so the catch-all does not swallow it.
@router.get("/plants")
def get_plants(db: Session = Depends(get_db)):
    return {"lookup": "plants", "values": plant_names(db)}


@router.get("/{lookup_name}")
def get_lookup(lookup_name: str):
    values = LOOKUPS.get(lookup_name)
    if values is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Lookup '{lookup_name}' not found")
    return {"lookup": lookup_name, "values": values}
