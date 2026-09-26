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
  /**
   * The scope this rule was written at, narrowest first. Both null (with
   * machine_type null too) is the global rule everything falls back to. A rule
   * carries at most one of the two — a sensor already belongs to one machine.
   */
  sensor_id: string | null;
  equipment_id: string | null;
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

/**
 * One sensor a limit could be written for.
 *
 * The API lists every sensor, not only those that already have a rule: a
 * coverage view built from the rules alone can show which sensors have their
 * own limit but never which ones fall back, and the second half is the
 * question being asked.
 */
export interface ThresholdScopeSensor {
  id: string;
  label: string;
  machine_name: string | null;
  machine_type: string | null;
  equipment_id: string | null;
}

export interface ThresholdRuleList {
  items: ThresholdRule[];
  rule_types: Record<string, ThresholdRuleTypeInfo>;
  overridden_channels: number[];
  sensors: ThresholdScopeSensor[];
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
  /** Mutually exclusive; the API rejects a payload carrying both. */
  sensor_id?: string | null;
  equipment_id?: string | null;
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
