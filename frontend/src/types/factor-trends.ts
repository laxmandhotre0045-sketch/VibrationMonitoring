export interface FactorTrendSeries {
  feature_code: string;
  feature_name: string;
  unit: string;
  value: number;
  status: string;
  trend_x: number[];
  trend_y: number[];
}

export interface UploadFactorTrendsResponse {
  upload_id: string;
  sensor_id: string;
  channel: number;
  features_status: string;
  sampling_rate_hz: number;
  factors: FactorTrendSeries[];
}
