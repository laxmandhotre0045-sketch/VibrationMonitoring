import type { FeatureCompareItem, FeatureStatusItem } from "@/types/features";
import {
  FEATURE_CATEGORY_LABELS,
  FEATURE_CATEGORY_ORDER,
  VIBRATION_FEATURE_CATALOG,
  formatFeatureUnit,
  getFeatureDefinition,
  resolveVibrationFeatureKey,
  type VibrationFeatureCategory,
  type VibrationFeatureKey,
} from "./vibration-features";

export interface GroupedFeatureItems {
  category: VibrationFeatureCategory;
  label: string;
  items: FeatureStatusItem[];
}

export interface GroupedCompareItems {
  category: VibrationFeatureCategory;
  label: string;
  items: FeatureCompareItem[];
}

function resolveItemKey(item: { feature: string; feature_key?: string }): VibrationFeatureKey | null {
  return resolveVibrationFeatureKey(item.feature_key ?? item.feature);
}

export function enrichFeatureStatusItems(items: FeatureStatusItem[]): FeatureStatusItem[] {
  const byKey = new Map<VibrationFeatureKey, FeatureStatusItem>();

  for (const item of items) {
    const key = resolveItemKey(item);
    if (!key) continue;
    const def = getFeatureDefinition(key);
    byKey.set(key, {
      ...item,
      feature_key: key,
      feature: def.label,
      unit: item.unit && item.unit !== "-" ? item.unit : def.unit,
      category: def.category,
    });
  }

  return VIBRATION_FEATURE_CATALOG.map((def) => {
    const existing = byKey.get(def.key);
    if (existing) return existing;
    return {
      feature: def.label,
      feature_key: def.key,
      value: null,
      unit: def.unit,
      status: "no_baseline" as const,
      category: def.category,
    };
  });
}

export function enrichFeatureCompareItems(items: FeatureCompareItem[]): FeatureCompareItem[] {
  const byKey = new Map<VibrationFeatureKey, FeatureCompareItem>();

  for (const item of items) {
    const key = resolveItemKey(item);
    if (!key) continue;
    const def = getFeatureDefinition(key);
    byKey.set(key, {
      ...item,
      feature_key: key,
      feature: def.label,
      unit: item.unit && item.unit !== "-" ? item.unit : def.unit,
      category: def.category,
    });
  }

  return VIBRATION_FEATURE_CATALOG.map((def) => {
    const existing = byKey.get(def.key);
    if (existing) return existing;
    return {
      feature: def.label,
      feature_key: def.key,
      upload_value: null,
      baseline_value: null,
      difference_percent: null,
      status: "no_baseline" as const,
      unit: def.unit,
      category: def.category,
    };
  });
}

export function groupFeatureStatusItems(items: FeatureStatusItem[]): GroupedFeatureItems[] {
  const enriched = enrichFeatureStatusItems(items);
  return FEATURE_CATEGORY_ORDER.map((category) => ({
    category,
    label: FEATURE_CATEGORY_LABELS[category],
    items: enriched.filter((item) => item.category === category),
  })).filter((group) => group.items.length > 0);
}

export function groupFeatureCompareItems(items: FeatureCompareItem[]): GroupedCompareItems[] {
  const enriched = enrichFeatureCompareItems(items);
  return FEATURE_CATEGORY_ORDER.map((category) => ({
    category,
    label: FEATURE_CATEGORY_LABELS[category],
    items: enriched.filter((item) => item.category === category),
  })).filter((group) => group.items.length > 0);
}

export function formatFeatureValue(value: number | string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "—";
    return value.toFixed(Math.abs(value) >= 1 ? 2 : 4);
  }
  return String(value);
}

export function formatCompareValue(value: number | null | undefined, unit?: string): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const suffix = unit && unit !== "-" ? ` ${unit}` : "";
  return `${value.toFixed(Math.abs(value) >= 1 ? 2 : 4)}${suffix}`;
}

export { formatFeatureUnit };
