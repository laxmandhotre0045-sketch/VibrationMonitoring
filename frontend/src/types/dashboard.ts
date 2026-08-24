export type EquipmentHealthStatus = "critical" | "warning" | "normal" | "no_baseline" | "no_data";

export interface FleetCounts {
  total: number;
  critical: number;
  warning: number;
  normal: number;
  no_data: number;
  average_health_score: number | null;
}

export interface EquipmentHealth {
  equipment_id: string;
  machine_name: string;
  machine_id: string | null;
  plant_name: string;
  area: string;
  line: string;
  machine_type: string;
  status: EquipmentHealthStatus;
  health_score: number | null;
  last_upload_at: string | null;
  worst_feature_name: string | null;
}

export interface DashboardAlert {
  equipment_id: string;
  machine_name: string;
  plant_name: string;
  sensor_id: string;
  channel: number;
  feature_code: string;
  feature_name: string | null;
  status: string;
  value: number;
  unit: string;
  computed_at: string;
}

export interface DashboardActivity {
  upload_id: string;
  equipment_id: string;
  machine_name: string;
  mounting_location: string;
  original_filename: string | null;
  parse_status: string;
  features_status: string;
  created_at: string;
}

export interface DashboardSummary {
  counts: FleetCounts;
  equipment_health: EquipmentHealth[];
  alerts: DashboardAlert[];
  recent_activity: DashboardActivity[];
}
