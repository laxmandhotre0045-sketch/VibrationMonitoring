import type { GraphThresholdSet } from "./threshold-overlay";

/** Mirrors backend `feature_threshold_rules` seed (display Y-axis values for overlays). */
type FeatureRuleType =
  | "absolute_max"
  | "absolute_db"
  | "range"
  | "percent_rms"
  | "percent_baseline";

interface FeatureThresholdRuleSeed {
  ruleType: FeatureRuleType;
  normalMax?: number;
  warningMax?: number;
  normalMin?: number;
  warningMin?: number;
  criticalPercent?: number;
}

const FEATURE_THRESHOLD_RULES: Record<string, FeatureThresholdRuleSeed> = {
  rms: { ruleType: "absolute_max", normalMax: 0.01, warningMax: 0.02 },
  peak: { ruleType: "absolute_max", normalMax: 0.05, warningMax: 0.1 },
  crest_factor: { ruleType: "range", normalMax: 3.0, warningMax: 5.0, normalMin: 1.4, warningMin: 1.4 },
  kurtosis: { ruleType: "absolute_max", normalMax: 3.5, warningMax: 5.0 },
  fft_band_energy_0_500: { ruleType: "percent_baseline", normalMax: 120, warningMax: 150, criticalPercent: 150 },
  fft_band_energy: { ruleType: "percent_baseline", normalMax: 120, warningMax: 150, criticalPercent: 150 },
  amplitude_1x: { ruleType: "percent_rms", normalMax: 20, warningMax: 40 },
  amplitude_2x: { ruleType: "percent_rms", normalMax: 10, warningMax: 20 },
  amplitude_3x: { ruleType: "percent_rms", normalMax: 5, warningMax: 15 },
  envelope_rms: { ruleType: "percent_baseline", normalMax: 100, warningMax: 125, criticalPercent: 150 },
  noise_floor: { ruleType: "absolute_db", normalMax: -60, warningMax: -54 },
};

const RULE_CODE_ALIASES: Record<string, string> = {
  fft_band_energy: "fft_band_energy_0_500",
};

export interface FeatureThresholdContext {
  channelRms?: number | null;
  baselineValue?: number | null;
}

function ruleForFeatureCode(featureCode: string): FeatureThresholdRuleSeed | undefined {
  const code = RULE_CODE_ALIASES[featureCode] ?? featureCode;
  return FEATURE_THRESHOLD_RULES[code] ?? FEATURE_THRESHOLD_RULES[featureCode];
}

function criticalAboveWarning(warning: number, rule: FeatureThresholdRuleSeed): number {
  if (rule.ruleType === "absolute_db") {
    return warning + Math.max(Math.abs(warning) * 0.1, 4);
  }
  if (rule.criticalPercent && rule.ruleType === "percent_baseline") {
    return warning;
  }
  return warning * 1.25;
}

/** Compute green / amber / red horizontal lines for a status feature trend chart. */
export function resolveFeatureThresholdLines(
  featureCode: string,
  context: FeatureThresholdContext = {}
): GraphThresholdSet {
  const rule = ruleForFeatureCode(featureCode);
  if (!rule) return {};

  const { channelRms, baselineValue } = context;

  switch (rule.ruleType) {
    case "absolute_max":
    case "absolute_db": {
      if (rule.normalMax === undefined || rule.warningMax === undefined) return {};
      return {
        normal: rule.normalMax,
        warning: rule.warningMax,
        critical: criticalAboveWarning(rule.warningMax, rule),
      };
    }
    case "range": {
      if (rule.normalMax === undefined || rule.warningMax === undefined) return {};
      return {
        normal: rule.normalMax,
        warning: rule.warningMax,
        critical: criticalAboveWarning(rule.warningMax, rule),
      };
    }
    case "percent_rms": {
      if (!channelRms || channelRms < 1e-30) return {};
      const normal = (channelRms * (rule.normalMax ?? 20)) / 100;
      const warning = (channelRms * (rule.warningMax ?? 40)) / 100;
      return {
        normal,
        warning,
        critical: criticalAboveWarning(warning, rule),
      };
    }
    case "percent_baseline": {
      if (!baselineValue || baselineValue < 1e-30) return {};
      const normal = (baselineValue * (rule.normalMax ?? 120)) / 100;
      const warning = (baselineValue * (rule.warningMax ?? 150)) / 100;
      const critPct = rule.criticalPercent ?? 150;
      return {
        normal,
        warning,
        critical: (baselineValue * critPct) / 100,
      };
    }
    default:
      return {};
  }
}

export function graphThresholdsToHealthMetric(thresholds: GraphThresholdSet): {
  normalThreshold?: number;
  warningThreshold?: number;
  dangerThreshold?: number;
} {
  return {
    normalThreshold: thresholds.normal,
    warningThreshold: thresholds.warning,
    dangerThreshold: thresholds.critical,
  };
}
