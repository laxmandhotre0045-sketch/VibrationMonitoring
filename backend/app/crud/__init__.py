from app.crud.equipment import (
    get_equipment_list, get_equipment_by_id, get_equipment_by_machine_id,
    create_equipment, update_equipment, delete_equipment, update_image_path,
    get_sensors_by_equipment, get_sensor_by_id, get_sensor_by_device_id,
    create_sensor, update_sensor,
    delete_sensor, compute_ai_readiness,
)
from app.crud.dashboard import get_dashboard_summary
