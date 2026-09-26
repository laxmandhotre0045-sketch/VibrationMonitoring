export interface Baseline {
  id: string;
  sensor_id: string;
  source_upload_id: string | null;
  name: string;
  description: string | null;
  labels: string[];
  original_filename: string;
  file_format: string;
  channel_count: number;
  sample_count: number;
  sampling_rate_hz: number;
  is_primary: boolean;
  captured_at: string | null;
  created_at: string;
  plot_count: number;
  plots_status: string;
}

export interface BaselineListResponse {
  sensor_id: string;
  total: number;
  primary_baseline_id: string | null;
  items: Baseline[];
}

export interface BaselineCreateFromUpload {
  name: string;
  description?: string | null;
  labels?: string[];
  set_as_primary?: boolean;
  captured_at?: string | null;
}

/**
 * Fields of `POST /api/v1/baselines/upload` — a CSV/PDF becoming a baseline
 * directly, without first going through the sensor-data upload flow.
 *
 * Unlike a promoted upload this stores no `sensor_data_uploads` row and
 * computes no feature rows: the baseline gets plots only.
 */
export interface BaselineFileUpload {
  sensorId: string;
  channelCount: number;
  name: string;
  description?: string | null;
  setAsPrimary?: boolean;
  file: File;
}

/**
 * How much the learned baseline in force for a sensor is worth — VIK-027.
 *
 * Every field that can be unknown arrives as null rather than as zero or an
 * empty string, and the shape here keeps that. A confidence of 0.0 and a
 * confidence nobody could compute are opposite situations; flattening them is
 * how "no baseline" comes to read as "perfectly normal".
 */
export type BaselineVersionState = "building" | "active" | "frozen" | "superseded";

export interface BaselineVersion {
  version: number;
  state: BaselineVersionState | string;
  reason: string | null;
  created_by: string | null;
  created_at: string | null;
  activated_at: string | null;
  frozen_at: string | null;
  superseded_at: string | null;
  superseded_by: number | null;
  age_days: number | null;
}

export interface BaselineHealth {
  sensor_id: string;
  available: boolean;
  /** Why not, when `available` is false. Always populated in that case. */
  reason: string | null;
  version: BaselineVersion | null;
  coverage: {
    rows: number;
    channels: number[];
    distinct_features: number;
    expected_rows: number | null;
    /** Null when nobody said how many features to expect. */
    fraction: number | null;
  };
  confidence: {
    min: number | null;
    median: number | null;
    max: number | null;
    low_confidence_rows: number;
    threshold: number;
  };
  samples: {
    min: number | null;
    median: number | null;
    max: number | null;
    minimum_required: number;
    preferred: number;
    below_preferred_rows: number;
  };
  freshness: {
    window_start: string | null;
    window_end: string | null;
    age_days: number | null;
    captures_since_window: number;
    stale: boolean;
    outgrown: boolean;
    stale_after_days: number;
  };
  exclusions: {
    quality_excluded_observations: number;
    other_shape_observations: number;
    mixed_population_rows: number;
  };
  /** Plain sentences, worst first, meant to be shown as written. */
  warnings: string[];
  history: BaselineVersion[];
}
