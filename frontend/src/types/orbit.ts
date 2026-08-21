/** Shapes returned by GET /api/v1/measurements/uploads/{id}/orbit. */

export const ORBIT_HARMONICS = [1, 2] as const;
export type OrbitHarmonic = (typeof ORBIT_HARMONICS)[number];

export const ORBIT_DISPLAY_REVS = [1, 2, 4, 8] as const;
export const ORBIT_FILTER_REVS = [4, 8, 16, 32] as const;
export const ORBIT_BANDWIDTHS = [0.5, 2, 5, 10, 20] as const;

export interface CasingOrbitResponse {
  upload_id: string;
  sensor_id: string;
  captured_at: string;
  original_filename: string | null;

  x_channel: number;
  y_channel: number;
  amplitude_unit: string;
  source_unit: string;
  is_displacement: boolean;

  sampling_rate_hz: number;
  sample_count: number;
  record_duration_s: number;

  harmonic: number;
  centre_hz: number;
  lower_hz: number;
  upper_hz: number;
  frequency_resolution_hz: number;
  requested_half_bandwidth_hz: number;
  effective_half_bandwidth_hz: number;
  effective_bandwidth_percent: number;
  bandwidth_sufficient: boolean;
  required_duration_s: number;
  integration_floor_hz: number;

  filter_revolutions: number;
  available_revolutions: number;
  display_revolutions: number;
  filter_duration_s: number;
  display_duration_s: number;

  /** FFT-derived estimate — never a measured tachometer reading. */
  estimated_shaft_hz: number | null;
  shaft_source: string;

  x_data: number[];
  y_data: number[];
  elapsed_s: number[];
  revolution: number[];
  unfiltered_x: number[] | null;
  unfiltered_y: number[] | null;
  point_count: number;
  peak_displacement_um: number;

  phase_reference: string;
  keyphasor_available: boolean;
  mounting_angle_configured: boolean;

  sensor_label: string | null;
  sensor_orientation: string | null;
  mounting_location: string | null;

  warnings: string[];
}

export interface CasingOrbitQuery {
  uploadId: string;
  xChannel: number;
  yChannel: number;
  harmonic: number;
  bandwidthPercent: number;
  /** Omit for auto (uses as many revolutions as the capture holds, up to 16). */
  filterRevolutions?: number;
  displayRevolutions: number;
  includeUnfiltered: boolean;
}
