import {
  VIBRATION_FEATURE_CATALOG,
  resolveVibrationFeatureKey,
  type VibrationFeatureKey,
} from "@/lib/vibration-features";
import {
  VIBRATION_CHANNEL_COUNT,
  type ThresholdConfig,
} from "@/types/vibration-settings";
import type { ResolvedThresholdRule, ThresholdRule } from "@/types/thresholds";

/**
 * Storage counts channels from zero — the same numbering the acquisition
 * pipeline and the Status (Health) tab use. Every Settings screen labels them
 * from one, so the two numbering schemes meet here and nowhere else.
 */
export function apiChannelToDisplay(channel: number): number {
  return channel + 1;
}

export function displayChannelToApi(channelNo: number): number {
  return channelNo - 1;
}

export function formatApiChannelLabel(channel: number): string {
  return `CH-${apiChannelToDisplay(channel)}`;
}

/**
 * Feature key -> backend feature code, learned from the rules themselves.
 *
 * The keys line up with the codes except for FFT band energy, where the code
 * carries the band (`fft_band_energy_0_500`). Deriving the map from the payload
 * keeps a future band change from needing a matching edit here.
 */
export function buildFeatureCodeMap(
  rules: ThresholdRule[]
): Map<VibrationFeatureKey, string> {
  const map = new Map<VibrationFeatureKey, string>();
  for (const rule of rules) {
    const key = resolveVibrationFeatureKey(rule.feature_code);
    if (key && !map.has(key)) {
      map.set(key, rule.feature_code);
    }
  }
  return map;
}

/**
 * Flatten the rule set into the channel x parameter grid the coverage matrix
 * reads. Channels without an override inherit the global rule, so a cell is
 * "configured" as soon as the feature has limits at all.
 */
export function rulesToThresholdConfigs(
  resolveFor: (channel: number | null, featureCode: string) => ResolvedThresholdRule | null,
  codeByKey: Map<VibrationFeatureKey, string>,
  channelCount: number = VIBRATION_CHANNEL_COUNT
): ThresholdConfig[] {
  const rows: ThresholdConfig[] = [];

  for (let channelNo = 1; channelNo <= channelCount; channelNo += 1) {
    for (const feature of VIBRATION_FEATURE_CATALOG) {
      const code = codeByKey.get(feature.key);
      if (!code) continue;

      const resolved = resolveFor(displayChannelToApi(channelNo), code);
      if (!resolved) continue;

      rows.push({
        channelNo,
        parameter: feature.key,
        warningThreshold: resolved.rule.normal_max,
        dangerThreshold: resolved.rule.warning_max,
        enabled: resolved.rule.is_active,
      });
    }
  }

  return rows;
}
