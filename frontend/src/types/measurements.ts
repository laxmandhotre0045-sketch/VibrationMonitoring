export const PLOT_TYPES = [
  "time_waveform",
  "circular_time_waveform",
  "fft_spectrum",
  "envelope_spectrum",
  "trend_plot",
] as const;

export type PlotType = (typeof PLOT_TYPES)[number];

export const PLOT_LABELS: Record<PlotType, string> = {
  time_waveform: "Time Waveform",
  circular_time_waveform: "Circular Time Waveform",
  fft_spectrum: "FFT Spectrum",
  envelope_spectrum: "Envelope Spectrum",
  trend_plot: "Trend Plot",
};

export interface PlotConfig {
  id: string;
  sensor_id: string;
  channel_count: number;
  active_channel: number;
  sampling_rate_hz: number;
  fft_lines: number;
  frequency_max_hz: number | null;
  data_type: string;
  enabled_plots: PlotType[];
  created_at: string;
  updated_at: string;
}

export interface PlotConfigInput {
  sensor_id: string;
  channel_count: number;
  active_channel?: number;
  sampling_rate_hz?: number;
  fft_lines?: number;
  frequency_max_hz?: number | null;
  data_type?: string;
  enabled_plots?: PlotType[];
}

export interface SensorDataUpload {
  id: string;
  sensor_id: string;
  channel_count: number;
  sample_count: number | null;
  parse_status: string;
  parse_error: string | null;
  created_at: string;
  parsed_at: string | null;
}

export interface PlotSeries {
  plot_type: PlotType;
  title: string;
  x_label: string;
  y_label: string;
  x: number[];
  y: number[];
  channel: number;
  metadata: Record<string, unknown>;
}

export interface AllPlotsResponse {
  upload_id: string;
  sensor_id: string;
  channel: number;
  plots: PlotSeries[];
}
