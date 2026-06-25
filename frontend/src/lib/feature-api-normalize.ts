import {
  resolveVibrationFeatureKey,
  getFeatureDefinition,
} from "@/lib/vibration-features";
import type {
  ChannelHealthOverviewData,
  FeatureCompareItem,
  FeatureCompareResponse,
  FeatureMonitorStatus,
  FeatureStatusItem,
  FeatureSummaryCounts,
  UploadFeaturesResponse,
} from "@/types/features";

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function readNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function normalizeStatus(value: unknown): FeatureMonitorStatus {
  const raw = String(value ?? "").toLowerCase();
  if (raw === "normal" || raw === "ok" || raw === "healthy") return "normal";
  if (raw === "warning" || raw === "caution") return "warning";
  if (raw === "critical" || raw === "danger" || raw === "alarm") return "critical";
  if (raw === "no_baseline" || raw === "no baseline" || raw === "none") return "no_baseline";
  return "no_baseline";
}

function normalizeSummary(data: Record<string, unknown>, itemCount: number): FeatureSummaryCounts {
  const summary = asRecord(data.summary ?? data.counts ?? data);
  return {
    total: readNumber(summary.total) ?? readNumber(summary.total_features) ?? itemCount,
    normal: readNumber(summary.normal) ?? 0,
    warning: readNumber(summary.warning) ?? 0,
    critical: readNumber(summary.critical) ?? 0,
    no_baseline: readNumber(summary.no_baseline) ?? readNumber(summary.noBaseline) ?? 0,
  };
}

function normalizeChannelOverview(
  data: Record<string, unknown>,
  baselineId?: string | null,
  baselineName?: string | null
): ChannelHealthOverviewData {
  const overview = asRecord(data.channel_overview ?? data.channel_health ?? data.overview ?? data);
  return {
    health_state: String(
      overview.health_state ?? overview.healthState ?? overview.state ?? "Unknown"
    ),
    feature_count:
      readNumber(overview.feature_count) ??
      readNumber(overview.featureCount) ??
      0,
    computed_at:
      typeof overview.computed_at === "string"
        ? overview.computed_at
        : typeof overview.computedAt === "string"
          ? overview.computedAt
          : null,
    baseline_name:
      typeof overview.baseline_name === "string"
        ? overview.baseline_name
        : baselineName ?? null,
    baseline_id:
      typeof overview.baseline_id === "string"
        ? overview.baseline_id
        : baselineId ?? null,
  };
}

function normalizeFeatureStatusItem(raw: Record<string, unknown>): FeatureStatusItem {
  const rawKey = String(
    raw.feature_key ?? raw.featureKey ?? raw.feature ?? raw.name ?? raw.parameter ?? ""
  );
  const key = resolveVibrationFeatureKey(rawKey);
  const def = key ? getFeatureDefinition(key) : null;

  return {
    feature: def?.label ?? String(raw.feature ?? raw.name ?? raw.parameter ?? "—"),
    feature_key: key ?? undefined,
    category: def?.category,
    value: readNumber(raw.value ?? raw.latest ?? raw.upload_value) ?? (raw.value as string | null) ?? null,
    unit: typeof raw.unit === "string" ? raw.unit : def?.unit,
    status: normalizeStatus(raw.status),
    caution_limit: readNumber(raw.caution_limit ?? raw.cautionLimit ?? raw.warning_threshold),
    warning_limit: readNumber(raw.warning_limit ?? raw.warningLimit ?? raw.danger_threshold),
  };
}

function normalizeCompareItem(raw: Record<string, unknown>): FeatureCompareItem {
  const rawKey = String(raw.feature_key ?? raw.featureKey ?? raw.feature ?? raw.name ?? "");
  const key = resolveVibrationFeatureKey(rawKey);
  const def = key ? getFeatureDefinition(key) : null;

  return {
    feature: def?.label ?? String(raw.feature ?? raw.name ?? "—"),
    feature_key: key ?? undefined,
    category: def?.category,
    upload_value: readNumber(raw.upload_value ?? raw.uploadValue ?? raw.value),
    baseline_value: readNumber(raw.baseline_value ?? raw.baselineValue),
    difference_percent: readNumber(
      raw.difference_percent ?? raw.differencePercent ?? raw.delta_percent ?? raw.deltaPercent
    ),
    status: normalizeStatus(raw.status),
    unit: typeof raw.unit === "string" ? raw.unit : def?.unit,
  };
}

export function normalizeUploadFeaturesResponse(
  data: unknown,
  fallback?: { uploadId: string; channel: number; baselineId?: string; baselineName?: string }
): UploadFeaturesResponse {
  const root = asRecord(data);
  const itemsRaw = root.items ?? root.features ?? root.parameters ?? [];
  const items = Array.isArray(itemsRaw)
    ? itemsRaw.map((item) => normalizeFeatureStatusItem(asRecord(item)))
    : [];

  return {
    upload_id: String(root.upload_id ?? fallback?.uploadId ?? ""),
    channel: readNumber(root.channel) ?? fallback?.channel ?? 0,
    items,
    summary: normalizeSummary(root, items.length),
    channel_overview: normalizeChannelOverview(
      root,
      fallback?.baselineId,
      fallback?.baselineName
    ),
  };
}

export function normalizeFeatureCompareResponse(
  data: unknown,
  fallback?: { uploadId: string; channel: number; baselineId?: string; baselineName?: string }
): FeatureCompareResponse {
  const root = asRecord(data);
  const itemsRaw = root.items ?? root.features ?? root.comparisons ?? [];
  const items = Array.isArray(itemsRaw)
    ? itemsRaw.map((item) => normalizeCompareItem(asRecord(item)))
    : [];

  return {
    upload_id: String(root.upload_id ?? fallback?.uploadId ?? ""),
    baseline_id:
      typeof root.baseline_id === "string"
        ? root.baseline_id
        : fallback?.baselineId ?? null,
    channel: readNumber(root.channel) ?? fallback?.channel ?? 0,
    items,
    summary: normalizeSummary(root, items.length),
    channel_overview: normalizeChannelOverview(
      root,
      fallback?.baselineId,
      fallback?.baselineName
    ),
  };
}

export function formatDifferencePercent(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(0)}%`;
}
