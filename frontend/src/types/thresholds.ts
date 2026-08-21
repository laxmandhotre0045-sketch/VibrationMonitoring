import type { VibrationFeatureKey } from "@/lib/vibration-features";

/**
 * The two limits every screen renames.
 *
 * The evaluator crosses `normal_max` first and `warning_max` second. Settings
 * has always called those "Warning" and "Danger"; the health table calls them
 * "Caution" and "Warning". The API ships `limit_labels` per rule so the naming
 * lives in one place — prefer it over hard-coding either pair.
 */
export type ThresholdRuleType =
  | "absolute_max"
  | "absolute_db"
  | "range"
  | "percent_rms"
  | "percent_baseline";

export type ThresholdLimitField =
  | "normal_max"
  | "warning_max"
  | "normal_min"
  | "warning_min";

export interface ThresholdRuleTypeInfo {
  label: string;
  unit_kind: "engineering" | "db" | "percent";
  description: string;
  uses: ThresholdLimitField[];
}

export interface ThresholdRule {
  id: string;
  feature_code: string;
  feature_name: string | null;
  unit: string | null;
  rule_type: ThresholdRuleType;
  machine_type: string | null;
  /** null means the rule applies to every channel without an override. */
  channel: number | null;
  normal_max: number | null;
  warning_max: number | null;
  normal_min: number | null;
  warning_min: number | null;
  metadata: Record<string, unknown>;
  is_active: boolean;
  updated_at: string | null;
  updated_by: string | null;
  is_default: boolean;
  limit_labels: Partial<Record<ThresholdLimitField, string>>;
}

export interface ThresholdRuleList {
  items: ThresholdRule[];
  rule_types: Record<string, ThresholdRuleTypeInfo>;
  overridden_channels: number[];
}

export interface ThresholdRuleUpdate {
  normal_max?: number | null;
  warning_max?: number | null;
  normal_min?: number | null;
  warning_min?: number | null;
  is_active?: boolean;
  metadata?: Record<string, unknown>;
}

export interface ThresholdRuleCreate extends ThresholdRuleUpdate {
  feature_code: string;
  channel?: number | null;
  machine_type?: string | null;
  rule_type?: ThresholdRuleType;
}

export interface ThresholdRuleBulkItem extends ThresholdRuleUpdate {
  id: string;
}

/**
 * A rule resolved for one channel: the override if the channel has one,
 * otherwise the global rule it inherits.
 */
export interface ResolvedThresholdRule {
  featureKey: VibrationFeatureKey | null;
  featureCode: string;
  rule: ThresholdRule;
  /** The row that would be written for this channel, or null while inherited. */
  override: ThresholdRule | null;
  global: ThresholdRule | null;
  isOverridden: boolean;
}
