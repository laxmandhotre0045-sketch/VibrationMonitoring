export const HEALTH_CHANNEL_COUNT = 8;

export type HealthMetricKey =
  | "rms"
  | "vrms"
  | "crest_factor"
  | "skew"
  | "kurtosis"
  | "peak"
  | "transients"
  | "saturation"
  | "temperature"
  | "battery_health";

export type HealthStatusCardKey =
  | "rms"
  | "vrms"
  | "skew"
  | "crest_factor"
  | "transients"
  | "saturation"
  | "temperature";

export const HEALTH_STATUS_CARD_KEYS: HealthStatusCardKey[] = [
  "rms",
  "vrms",
  "skew",
  "crest_factor",
  "transients",
  "saturation",
  "temperature",
];

export const TREND_TAB_METRIC_KEYS: HealthMetricKey[] = [
  "rms",
  "vrms",
  "crest_factor",
  "skew",
  "kurtosis",
  "temperature",
];

export type HealthStatusLevel = "healthy" | "warning" | "danger" | "neutral";

export interface HealthMetricTrend {
  key: HealthMetricKey;
  label: string;
  unit: string;
  value: number | null;
  trendX: number[];
  trendY: number[];
  available: boolean;
  status: HealthStatusLevel;
  warningThreshold?: number;
  dangerThreshold?: number;
}

export interface HealthThresholdRow {
  parameter: string;
  latest: string;
  deltaVsPrior: string;
  rangePeriod: string;
  cautionLimit: string;
  warningLimit: string;
  status: HealthStatusLevel;
}

export interface HealthStatusSnapshot {
  channel: number;
  channelLabel: string;
  metrics: HealthMetricTrend[];
  statusCardMetrics: HealthMetricTrend[];
  thresholdRows: HealthThresholdRow[];
  hasThresholds: boolean;
  bannerMessage: string;
  cautionThreshold?: number;
  warningThreshold?: number;
}
