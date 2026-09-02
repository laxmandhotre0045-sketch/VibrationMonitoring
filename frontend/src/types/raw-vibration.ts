/** Raw 25 kSPS vibration snapshots — GET /api/v1/measurements/raw/* */

export const RAW_WINDOW_SIZES = [1000, 2500, 5000, 12500, 25000] as const;

/** One row of the raw CSV: timestamp_ plus the requested channels. */
export interface RawSample {
  timestamp_: number;
  [channel: string]: number;
}

export interface RawSamplesResponse {
  upload_id: string;
  sensor_id: string;
  device_id: string | null;
  original_filename: string | null;
  measured_at: string | null;
  captured_at: string;

  sampleRate: number;
  channelCount: number;

  offset: number;
  limit: number;
  returned: number;
  total_samples: number;
  has_more: boolean;
  channels: number[];

  /** Always true — this endpoint never returns processed data. */
  is_raw: boolean;
  samples: RawSample[];
}

export interface RawSnapshotSummary {
  upload_id: string;
  sensor_id: string;
  original_filename: string | null;
  captured_at: string;
  measured_at: string | null;
  sample_count: number | null;
  channel_count: number;
  source: string | null;
  has_raw_samples: boolean;
}

export interface RawSnapshotListResponse {
  sensor_id: string;
  total: number;
  items: RawSnapshotSummary[];
}

export interface RawSamplesQuery {
  uploadId: string;
  offset?: number;
  limit?: number;
  /** Channel indexes to fetch. Fetching all eight is ~3.5 MB per second of data. */
  channels?: number[];
}

/** Time-domain statistics for one channel of one snapshot. */
export interface RawStatistics {
  rms: number;
  peak: number;
  peak_to_peak: number;
  crest_factor: number;
  /** Excess kurtosis — a Gaussian signal reads 0, not 3. */
  kurtosis: number;
  skewness: number;
}

/** FFT of one channel, computed by the backend's shared signal-processing code. */
export interface RawSpectrum {
  frequencies: number[];
  amplitudes: number[];
  dominant_frequency_hz: number;
  dominant_amplitude: number;
  line_count: number;
  returned_points: number;
  block_size: number;
  averages: number;
  frequency_resolution_hz: number;
}

export interface RawAnalysisResponse {
  upload_id: string;
  sensor_id: string;
  device_id: string | null;
  original_filename: string | null;
  captured_at: string;
  measured_at: string | null;
  channel: number;
  channel_label: string | null;
  machine_axis: string | null;
  signal_type: string | null;
  sample_rate_hz: number;
  sample_count: number;
  channel_count: number;
  spectrum: RawSpectrum;
  statistics: RawStatistics;
}
