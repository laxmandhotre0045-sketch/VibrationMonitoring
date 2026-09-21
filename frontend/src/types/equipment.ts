import { z } from "zod";

export const sensorSchema = z.object({
  id: z.string().optional(),
  sensor_type: z.string().min(1, "Sensor type is required"),
  mounting_location: z.string().min(1, "Mounting location is required"),
  orientation: z.string().min(1, "Orientation is required"),
  mounting_method: z.string().optional().nullable(),
  sensitivity: z.coerce.number().optional().nullable(),
  sensitivity_unit: z.string().optional().nullable(),
  sampling_rate: z.string().optional().nullable(),
  sampling_rate_custom: z.coerce.number().int().optional().nullable(),
  frequency_range: z.string().optional().nullable(),
  frequency_range_custom_min: z.coerce.number().int().optional().nullable(),
  frequency_range_custom_max: z.coerce.number().int().optional().nullable(),
  is_active: z.boolean().default(true),
});

/**
 * A number the user may simply not know yet.
 *
 * `z.coerce.number()` turns an empty input into `0`, so a blank optional field
 * that also carries `.positive()` fails validation — and react-hook-form
 * swallows a rejected submit, which is what made Save look dead when the
 * rotating-component fields were left empty. Blank, null, and unparseable
 * input all collapse to `null` here, before any numeric check runs.
 */
function optionalNumber(refine?: (schema: z.ZodNumber) => z.ZodNumber) {
  const base = z.coerce.number();
  return z.preprocess((value) => {
    if (value === "" || value === null || value === undefined) return null;
    if (typeof value === "number" && Number.isNaN(value)) return null;
    return value;
  }, (refine ? refine(base) : base).nullable().optional());
}

export const equipmentSchema = z.object({
  // Location & Hierarchy
  plant_name: z.string().optional().nullable(),
  area: z.string().optional().nullable(),
  line: z.string().optional().nullable(),

  // Asset Identification
  machine_name: z.string().optional().nullable(),
  machine_id: z.string().optional().nullable(),
  machine_type: z.string().optional().nullable(),
  machine_criticality: z.string().optional().nullable(),
  manufacturer: z.string().optional().nullable(),
  model: z.string().optional().nullable(),
  serial_number: z.string().optional().nullable(),

  // Mechanical Details
  rated_power_kw: z.coerce.number().positive().optional().nullable(),
  rated_rpm: z.coerce.number().int().positive().optional().nullable(),
  drive_type: z.string().optional().nullable(),
  load_type: z.string().optional().nullable(),
  foundation_type: z.string().optional().nullable(),
  coupling_details: z.string().optional().nullable(),

  // Rotating Components — every field here is optional: equipment saves with
  // the whole Bearing Details / Rotating Components step left blank.
  bearing_details: z.string().optional().nullable(),
  bearing_number_de: z.string().optional().nullable(),
  bearing_number_nde: z.string().optional().nullable(),
  // Bearing ID in the fault-frequency catalogue, set when the fitted bearing is
  // matched against it. Null means the bearing is recorded as free text only.
  bearing_de_catalog_id: optionalNumber((n) => n.int().positive()),
  bearing_nde_catalog_id: optionalNumber((n) => n.int().positive()),
  gearbox_ratio: optionalNumber((n) => n.positive()),
  gear_teeth: optionalNumber((n) => n.int().positive()),
  motor_pole_count: optionalNumber((n) => n.int()),
  fan_blades: optionalNumber((n) => n.int().positive()),
  pump_vanes: optionalNumber((n) => n.int().positive()),
  direction_of_rotation: z.string().optional().nullable(),

  // Operating Conditions
  operating_speed_min: z.coerce.number().int().optional().nullable(),
  operating_speed_max: z.coerce.number().int().optional().nullable(),
  load_range_min: z.coerce.number().optional().nullable(),
  load_range_max: z.coerce.number().optional().nullable(),
  normal_operating_load: z.coerce.number().optional().nullable(),
  process_details: z.string().optional().nullable(),
  operating_environment: z.array(z.string()).optional().nullable(),

  // Lubrication & Maintenance
  lubrication_type: z.string().optional().nullable(),
  installation_date: z.string().optional().nullable(),
  last_maintenance_date: z.string().optional().nullable(),
  maintenance_notes: z.string().optional().nullable(),

  // AI Readiness
  asset_status: z.string().optional().nullable(),
  machine_train_configured: z.boolean().optional(),
  bearing_database_mapped: z.boolean().optional(),
  operating_mode_configured: z.boolean().optional(),

  // Sensors
  sensors: z.array(sensorSchema).optional().default([]),
});

export type EquipmentFormData = z.infer<typeof equipmentSchema>;
export type SensorFormData = z.infer<typeof sensorSchema>;

export interface EquipmentListItem {
  id: string;
  plant_name: string;
  area: string;
  line: string;
  machine_name: string;
  machine_id: string;
  machine_type: string;
  machine_criticality: string;
  manufacturer?: string;
  asset_status?: string;
  equipment_image_path?: string;
  created_at: string;
}

export interface EquipmentOut extends EquipmentFormData {
  id: string;
  equipment_image_path?: string;
  created_at: string;
  updated_at: string;
}

export interface AIReadiness {
  equipment_id: string;
  score_percent: number;
  machine_train_configured: boolean;
  asset_status_set: boolean;
  sensor_coverage: boolean;
  bearing_database_mapped: boolean;
  operating_mode_configured: boolean;
}

export interface PaginatedEquipment {
  total: number;
  page: number;
  page_size: number;
  items: EquipmentListItem[];
}

export const CRITICALITY_COLORS: Record<string, string> = {
  Low: "bg-machine-healthy/10 text-machine-healthy border border-machine-healthy/25",
  Medium: "bg-machine-warning/10 text-machine-warning border border-machine-warning/25",
  High: "bg-machine-critical/10 text-machine-critical border border-machine-critical/25",
  Critical: "bg-machine-critical/15 text-machine-critical border border-machine-critical/30",
};

export const CRITICALITY_DOT: Record<string, string> = {
  Low: "bg-machine-healthy",
  Medium: "bg-machine-warning",
  High: "bg-machine-critical",
  Critical: "bg-machine-critical",
};

export const ASSET_STATUS_COLORS: Record<string, string> = {
  Active: "bg-machine-healthy/10 text-machine-healthy border border-machine-healthy/25",
  "Under Maintenance": "bg-machine-warning/10 text-machine-warning border border-machine-warning/25",
  Inactive: "bg-machine-offline/10 text-machine-offline border border-machine-offline/25",
  Offline: "bg-machine-offline/10 text-machine-offline border border-machine-offline/25",
};
