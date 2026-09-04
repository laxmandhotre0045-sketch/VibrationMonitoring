import type { EquipmentFormData } from "@/types/equipment";

export const FORM_STEPS = [
  { id: 1, label: "Basic Details", shortLabel: "Basic" },
  { id: 2, label: "Mechanical Details", shortLabel: "Mechanical" },
  { id: 3, label: "Rotating Components", shortLabel: "Rotating" },
  { id: 4, label: "Operating & Process", shortLabel: "Operating" },
  { id: 5, label: "Sensors & Orientation", shortLabel: "Sensors" },
  { id: 6, label: "Review & Save", shortLabel: "Review" },
] as const;

const STEP_FIELDS: Record<number, (keyof EquipmentFormData)[]> = {
  1: ["plant_name", "area", "line", "machine_name", "machine_id", "machine_type", "machine_criticality", "manufacturer", "model", "serial_number"],
  2: ["rated_power_kw", "rated_rpm", "drive_type", "load_type", "foundation_type", "coupling_details"],
  3: ["bearing_details", "bearing_number_de", "bearing_number_nde", "gearbox_ratio", "motor_pole_count", "direction_of_rotation"],
  4: ["operating_speed_min", "operating_speed_max", "load_range_min", "load_range_max", "process_details", "lubrication_type"],
  5: [],
  6: ["asset_status"],
};

/**
 * Which form fields live on a given step.
 *
 * Exposed so a rejected submit can send the user to the step holding the
 * offending field instead of leaving them on Review with a dead Save button.
 */
export function stepFieldNames(stepId: number): string[] {
  if (stepId === 5) return ["sensors"];
  return (STEP_FIELDS[stepId] ?? []) as string[];
}

function isFilled(value: unknown): boolean {
  if (value === null || value === undefined || value === "") return false;
  if (Array.isArray(value)) return value.length > 0;
  return true;
}

export function getStepCompletion(data: EquipmentFormData, stepId: number): number {
  if (stepId === 5) {
    const sensors = data.sensors || [];
    if (sensors.length === 0) return 0;
    const filled = sensors.filter((s) => s.sensor_type && s.mounting_location && s.orientation).length;
    return Math.round((filled / Math.max(sensors.length, 1)) * 100);
  }
  const fields = STEP_FIELDS[stepId] || [];
  if (fields.length === 0) return stepId === 6 ? 50 : 0;
  const filled = fields.filter((f) => isFilled(data[f])).length;
  return Math.round((filled / fields.length) * 100);
}

export function getFormCompletion(data: EquipmentFormData): number {
  const steps = [1, 2, 3, 4, 5];
  const total = steps.reduce((sum, id) => sum + getStepCompletion(data, id), 0);
  return Math.round(total / steps.length);
}

export function getDataCompleteness(data: EquipmentFormData): number {
  return getFormCompletion(data);
}

export function getSensorCoverage(data: EquipmentFormData): number {
  const sensors = data.sensors || [];
  if (sensors.length === 0) return 0;
  const configured = sensors.filter((s) => s.sensor_type && s.mounting_location && s.orientation).length;
  const ideal = Math.max(sensors.length, 3);
  return Math.min(100, Math.round((configured / ideal) * 100));
}

export function getDiagnosticReadiness(data: EquipmentFormData): number {
  const checks = [
    !!data.machine_type,
    !!data.rated_rpm,
    !!data.bearing_number_de || !!data.bearing_number_nde,
    (data.sensors?.length || 0) > 0,
    !!data.operating_speed_min && !!data.operating_speed_max,
  ];
  return Math.round((checks.filter(Boolean).length / checks.length) * 100);
}

export function getPMReadiness(data: EquipmentFormData): number {
  const checks = [
    !!data.machine_criticality,
    !!data.asset_status,
    !!data.lubrication_type || !!data.last_maintenance_date,
    !!data.installation_date,
    getFormCompletion(data) >= 60,
  ];
  return Math.round((checks.filter(Boolean).length / checks.length) * 100);
}

export function getAIReadinessScore(data: EquipmentFormData): number {
  return Math.round(
    (getDataCompleteness(data) + getSensorCoverage(data) + getDiagnosticReadiness(data) + getPMReadiness(data)) / 4
  );
}

export function getMissingAlerts(data: EquipmentFormData): string[] {
  const alerts: string[] = [];
  if (!data.plant_name) alerts.push("Plant hierarchy not configured");
  if (!data.machine_name) alerts.push("Machine identity not assigned");
  if (!data.machine_id) alerts.push("Asset code required for data correlation");
  if (!data.machine_type) alerts.push("Machine type required for diagnostic models");
  if (!data.machine_criticality) alerts.push("Criticality classification pending");
  if (!data.rated_rpm) alerts.push("Rated RPM needed for frequency calculations");
  if (!data.bearing_number_de && !data.bearing_number_nde) alerts.push("Bearing database not mapped");
  if ((data.sensors?.length || 0) === 0) alerts.push("Sensor mapping incomplete");
  if (!data.operating_speed_min) alerts.push("Operating envelope not defined");
  return alerts;
}

export function getSensorStatus(data: EquipmentFormData): { label: string; status: "complete" | "partial" | "empty" } {
  const count = data.sensors?.length || 0;
  if (count === 0) return { label: "Not configured", status: "empty" };
  const configured = data.sensors?.filter((s) => s.sensor_type && s.mounting_location).length || 0;
  if (configured === count) return { label: `${count} point(s) mapped`, status: "complete" };
  return { label: `${configured}/${count} configured`, status: "partial" };
}

export function getRecommendedActions(data: EquipmentFormData, activeStep: number): string[] {
  const actions: string[] = [];
  if (!data.machine_type) actions.push("Select machine type to load diagnostic profile");
  if (!data.rated_rpm) actions.push("Enter rated RPM for shaft frequency calculation");
  if (!data.bearing_number_de && activeStep >= 3) actions.push("Map bearing numbers for BPFO/BPFI analysis");
  if ((data.sensors?.length || 0) === 0 && activeStep >= 5) actions.push("Configure vibration sensor mounting points");
  if (getDiagnosticReadiness(data) >= 70) actions.push("Profile sufficient for FFT and bearing fault detection");
  if (actions.length === 0) actions.push("Continue building digital twin configuration");
  return actions.slice(0, 4);
}

export function getAssetStatusLabel(data: EquipmentFormData, isEdit: boolean): string {
  if (!isEdit && !data.machine_name) return "Draft";
  return data.asset_status || "Draft";
}
