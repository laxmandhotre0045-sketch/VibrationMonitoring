import type { HealthStatusLevel } from "@/types/health-status";
import type { HealthStatusSnapshot } from "@/types/health-status";
import type {
  ChannelHealthOverviewData,
  FeatureMonitorStatus,
  FeatureStatusItem,
  FeatureSummaryCounts,
} from "@/types/features";

export function mapHealthLevelToFeatureStatus(level: HealthStatusLevel): FeatureMonitorStatus {
  if (level === "healthy") return "normal";
  if (level === "warning") return "warning";
  if (level === "danger") return "critical";
  return "no_baseline";
}

export function buildFallbackFeatureItems(snapshot: HealthStatusSnapshot): FeatureStatusItem[] {
  return snapshot.statusCardMetrics.map((metric) => ({
    feature: metric.unit ? `${metric.label} (${metric.unit})` : metric.label,
    value: metric.value,
    unit: metric.unit,
    status: metric.available
      ? mapHealthLevelToFeatureStatus(metric.status)
      : "no_baseline",
    caution_limit: metric.warningThreshold ?? null,
    warning_limit: metric.dangerThreshold ?? null,
  }));
}

export function summarizeFeatureItems(items: FeatureStatusItem[]): FeatureSummaryCounts {
  const summary: FeatureSummaryCounts = {
    total: items.length,
    normal: 0,
    warning: 0,
    critical: 0,
    no_baseline: 0,
  };
  for (const item of items) {
    summary[item.status] += 1;
  }
  return summary;
}

export function deriveHealthState(summary: FeatureSummaryCounts): string {
  if (summary.critical > 0) return "Critical";
  if (summary.warning > 0) return "Warning";
  if (summary.total === 0) return "Unknown";
  if (summary.normal > 0) return "Normal";
  return "No Baseline";
}

export function buildFallbackChannelOverview(
  snapshot: HealthStatusSnapshot,
  summary: FeatureSummaryCounts,
  baselineName?: string | null,
  baselineId?: string | null
): ChannelHealthOverviewData {
  return {
    health_state: deriveHealthState(summary),
    feature_count: summary.total,
    computed_at: null,
    baseline_name: baselineName ?? null,
    baseline_id: baselineId ?? null,
  };
}
