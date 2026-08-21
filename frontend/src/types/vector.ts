/** Shapes returned by GET /api/v1/measurements/uploads/{id}/vector. */

export interface VectorBlock {
  block_index: number;
  start_sample: number;
  time_s: number;
  amplitude: number;
  /** Raw atan2 result; absolute only in an arbitrary sense — see phase_reference. */
  phase_deg: number;
  /** Phase against block 0. This is the meaningful quantity. */
  relative_phase_deg: number;
  is_reference: boolean;
}

export interface VectorDrift {
  phase_slope_deg_per_s: number | null;
  implied_frequency_offset_hz: number | null;
  amplitude_cv: number | null;
  linear_fit_r2: number | null;
  likely_bin_mismatch: boolean;
}

export interface FrequencyCandidate {
  label: string;
  frequency_hz: number;
  source: string;
  amplitude: number | null;
}

export interface VibrationVectorResponse {
  upload_id: string;
  sensor_id: string;
  channel: number;
  captured_at: string;
  original_filename: string | null;

  sampling_rate_hz: number;
  sample_count: number;
  window: string;
  block_size: number;
  block_step: number;
  block_count: number;
  overlap: number;
  block_duration_s: number;

  target_hz_requested: number;
  bin_hz: number;
  bin_index: number;
  frequency_resolution_hz: number;
  target_source: string;
  target_label: string;

  amplitude_unit: string;
  data_type: string;
  amplitude_min: number;
  amplitude_max: number;

  /** FFT-derived estimate. Never a measured tachometer reading. */
  estimated_shaft_hz: number | null;

  phase_reference: string;
  angle_convention: string;
  keyphasor_available: boolean;

  sensor_label: string | null;
  orientation: string | null;
  mounting_location: string | null;

  blocks: VectorBlock[];
  drift: VectorDrift;
  candidates: FrequencyCandidate[];
}

export interface VibrationVectorQuery {
  uploadId: string;
  channel: number;
  targetHz?: number;
  blockSize?: number;
  overlap?: number;
}

/** Block sizes offered in the UI. Larger blocks resolve low frequencies more precisely. */
export const VECTOR_BLOCK_SIZES = [512, 1024, 1600, 2048, 4096, 8192] as const;
