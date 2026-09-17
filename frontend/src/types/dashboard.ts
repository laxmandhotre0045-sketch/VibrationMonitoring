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

// --- MOM items 4, 5 and 6: AI analysis, summaries and questions ------------

export interface AIFinding {
  code: string;
  title: string;
  detail: string;
  severity: "critical" | "warning" | "advisory" | "informational";
  confidence: "high" | "medium" | "low";
  channel_index: number | null;
  evidence: Record<string, unknown>;
  /** What stops a true statement being used for a question it cannot answer. */
  caveat: string | null;
}

export interface AIAnalysis {
  generated_at: string;
  headline: string;
  findings: AIFinding[];
  cannot_conclude: string[];
  context_summary: Record<string, unknown>;
}

export interface AISummary {
  generated_at: string;
  headline: string;
  summary: string;
  suggestions: string[];
  /** "model" when a language model wrote the prose, "template" when the
   *  platform did. Shown to the reader rather than hidden. */
  source: "model" | "template";
  rejected_reason: string | null;
  model: string | null;
}

export interface AIAnswer {
  generated_at: string;
  question: string;
  answer: string;
  source: "model" | "refused" | "unavailable";
  refused_reason: string | null;
  grounded_on: string[];
  model: string | null;
}

export interface AIStatus {
  llm_configured: boolean;
  model: string | null;
}
