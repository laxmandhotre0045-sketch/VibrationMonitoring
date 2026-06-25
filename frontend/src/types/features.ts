import type { VibrationFeatureCategory, VibrationFeatureKey } from "@/lib/vibration-features";

export type FeatureMonitorStatus = "normal" | "warning" | "critical" | "no_baseline";

export interface FeatureStatusItem {
  feature: string;
  feature_key?: VibrationFeatureKey;
  category?: VibrationFeatureCategory;
  value: number | string | null;
  unit?: string;
  status: FeatureMonitorStatus;
  caution_limit?: number | null;
  warning_limit?: number | null;
}

export interface FeatureSummaryCounts {
  total: number;
  normal: number;
  warning: number;
  critical: number;
  no_baseline: number;
}

export interface ChannelHealthOverviewData {
  health_state: string;
  feature_count: number;
  computed_at: string | null;
  baseline_name: string | null;
  baseline_id: string | null;
}

export interface FeatureCompareItem {
  feature: string;
  feature_key?: VibrationFeatureKey;
  category?: VibrationFeatureCategory;
  upload_value: number | null;
  baseline_value: number | null;
  difference_percent: number | null;
  status: FeatureMonitorStatus;
  unit?: string;
}

export interface UploadFeaturesResponse {
  upload_id: string;
  channel: number;
  items: FeatureStatusItem[];
  summary: FeatureSummaryCounts;
  channel_overview: ChannelHealthOverviewData;
}

export interface FeatureCompareResponse {
  upload_id: string;
  baseline_id: string | null;
  channel: number;
  items: FeatureCompareItem[];
  summary?: FeatureSummaryCounts;
  channel_overview?: ChannelHealthOverviewData;
}
