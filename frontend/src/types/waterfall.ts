/** Shapes returned by GET /api/v1/measurements/waterfall. */

export const WATERFALL_MODES = ["last", "oldest", "random"] as const;
export type WaterfallMode = (typeof WATERFALL_MODES)[number];

export const WATERFALL_MODE_LABELS: Record<WaterfallMode, string> = {
  last: "Last N",
  oldest: "Oldest N",
  random: "Random",
};

/** Spectra the waterfall can stack — both are already produced by the plot pipeline. */
export const WATERFALL_SPECTRA = ["fft_spectrum", "envelope_spectrum"] as const;
export type WaterfallSpectrum = (typeof WATERFALL_SPECTRA)[number];

export const WATERFALL_SPECTRUM_LABELS: Record<WaterfallSpectrum, string> = {
  fft_spectrum: "FFT Spectrum",
  envelope_spectrum: "Envelope Spectrum",
};

export interface WaterfallPeak {
  frequency: number;
  amplitude: number;
}

export interface WaterfallCapture {
  /** 1-based position in stacking order (oldest -> newest). */
  capture_number: number;
  upload_id: string;
  original_filename: string | null;
  captured_at: string;
  channel: number;
  point_count: number;
  frequencies: number[];
  amplitudes: number[];
  peaks: WaterfallPeak[];
}

export interface WaterfallResponse {
  sensor_id: string;
  channel: number;
  plot_type: string;
  selection_mode: WaterfallMode;
  stacking: string;

  requested_count: number;
  returned_count: number;
  total_available: number;
  skipped_count: number;

  sampling_rate_hz: number;
  fft_lines: number | null;
  window: string;
  data_type: string;

  frequency_min_hz: number | null;
  frequency_max_hz: number | null;
  frequency_resolution_hz: number | null;
  amplitude_min: number | null;
  amplitude_max: number | null;

  x_label: string;
  y_label: string;
  z_label: string;

  sensor_label: string | null;
  orientation: string | null;
  mounting_location: string | null;

  captures: WaterfallCapture[];
}

export interface WaterfallQuery {
  sensorId: string;
  channel: number;
  count: number;
  mode: WaterfallMode;
  plotType: WaterfallSpectrum;
  maxPoints?: number;
  maxPeaks?: number;
  /** Keeps a random selection stable across refetches. */
  seed?: number;
}
