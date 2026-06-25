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
