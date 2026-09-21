import type { VibrationFeatureCategory, VibrationFeatureKey } from "@/lib/vibration-features";

/**
 * "not_assessed" is measured but deliberately not graded, and is distinct
 * from "no_baseline". No baseline means a judgement was wanted and could not
 * be made yet; not assessed means none was ever intended. Most of the 26
 * features added in VIK-018 to VIK-020 have no published limit, and a few --
 * dominant frequency, DC offset, skewness -- have no direction at all, so
 * "higher is worse" is simply false for them. Showing those as "No Baseline"
 * would imply that collecting more data fixes it. It does not.
 */
export type FeatureMonitorStatus =
  | "normal"
  | "warning"
  | "critical"
  | "no_baseline"
  | "not_assessed";

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
  not_assessed: number;
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
