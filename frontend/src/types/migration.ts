/** Shapes returned by GET /api/v1/measurements/one-x-migration. */

export const MIGRATION_COUNTS = [10, 20, 40, 80, 120] as const;

export interface ResponseEllipse {
  major_axis: number;
  minor_axis: number;
  orientation_deg: number;
  ellipticity: number;
}

export interface MigrationPoint {
  upload_id: string;
  captured_at: string;
  sequence: number;
  x_channel: number;
  y_channel: number;

  /** Magnitudes — always >= 0. The plot lives in the positive quadrant. */
  x_amplitude: number;
  y_amplitude: number;
  x_amplitude_g: number;
  y_amplitude_g: number;

  /** FFT-derived estimate, never a measured tachometer reading. */
  shaft_frequency_hz: number | null;
  shaft_rpm: number | null;
  speed_source: string;

  x_phase_deg: number | null;
  y_phase_deg: number | null;
  /** phase(Y) − phase(X). Relative only — there is no keyphasor. */
  relative_phase_deg: number | null;

  vector_amplitude: number;
  vh_ratio: number | null;
  bin_hz: number | null;
  frequency_resolution_hz: number | null;

  quality: "valid" | "uncertain" | "invalid";
  warnings: string[];
  ellipse: ResponseEllipse | null;
}

export interface MigrationSummary {
  valid_count: number;
  x_max: number;
  y_max: number;
  shaft_hz_min: number | null;
  shaft_hz_max: number | null;
}

export interface OneXMigrationResponse {
  sensor_id: string;
  x_channel: number;
  y_channel: number;
  harmonic: number;

  amplitude_unit: string;
  source_unit: string;
  is_displacement: boolean;

  selection_mode: string;
  requested_count: number;
  returned_count: number;
  total_available: number;
  skipped_count: number;
  stacking: string;

  sampling_rate_hz: number;
  keyphasor_available: boolean;
  is_shaft_centerline: boolean;

  sensor_label: string | null;
  sensor_orientation: string | null;
  mounting_location: string | null;

  points: MigrationPoint[];
  summary: MigrationSummary;
  warnings: string[];
}

export interface OneXMigrationQuery {
  sensorId: string;
  xChannel: number;
  yChannel: number;
  count: number;
  mode: string;
}
