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

// --- MOM items 10 and 12: when data arrived, and 7/30-day summaries ---------

export interface LastEntry {
  capture_id: string;
  upload_id: string;
  at: string;
  /** Seconds since the capture, computed server-side so a skewed client clock
   *  cannot be reported as stale data. */
  age_seconds: number | null;
  machine_name: string;
  sensor_location: string;
  original_filename: string | null;
  sample_count: number;
  channel_count: number;
  sample_rate_hz: number;
}

export interface EntryDate {
  date: string;
  count: number;
  first_at: string;
  last_at: string;
}

export interface ChannelTrend {
  channel_index: number;
  /** AC RMS — vibration with the sensor's standing DC bias removed. */
  rms_mean: number;
  rms_min: number;
  rms_max: number;
  /** Null whenever the data cannot support a trend; `trend_blocked_reason`
   *  then says why. Null is the normal case early in a deployment. */
  trend: number | null;
  direction: "rising" | "falling" | "flat" | "unknown";
  trend_blocked_reason: string | null;
}

export interface WindowSummary {
  days: number;
  captures: number;
  active_days: number;
  first_at: string | null;
  last_at: string | null;
  span_hours: number;
  /** Fraction of the window that actually holds data. Without showing this,
   *  20 captures over 40 minutes and over a week look identical. */
  coverage_fraction: number;
  channels: ChannelTrend[];
  note: string | null;
}

export interface CaptureHistory {
  generated_at: string;
  last_entry: LastEntry | null;
  entries_by_date: EntryDate[];
  windows: WindowSummary[];
}
