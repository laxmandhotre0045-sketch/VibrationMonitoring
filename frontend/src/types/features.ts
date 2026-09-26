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

/**
 * How far a capture's numbers can be trusted, from the data-quality checks.
 *
 * Ordered worst-last on purpose: these are the only four the API publishes, and
 * a screen switching on them can be exhaustive. `null` is a fifth state and not
 * one of these — it means nothing assessed the capture, which is not the same
 * as passing and must never be rendered as one.
 */
export type TrustLevel = "High" | "Medium" | "Low" | "Invalid";

export interface UploadFeaturesResponse {
  upload_id: string;
  channel: number;
  items: FeatureStatusItem[];
  summary: FeatureSummaryCounts;
  channel_overview: ChannelHealthOverviewData;
  /** null means unassessed — never treat it as a pass. */
  trust_level: TrustLevel | null;
  /** Checks that ran and did not pass. */
  failed_checks: string[];
  /** Checks that could not run at all — not failures, and not passes either. */
  not_assessed_checks: string[];
}

export interface FeatureCompareResponse {
  upload_id: string;
  baseline_id: string | null;
  channel: number;
  items: FeatureCompareItem[];
  summary?: FeatureSummaryCounts;
  channel_overview?: ChannelHealthOverviewData;
}
