import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { getUploadFactorTrends } from "@/api/measurements";
import { resolveVibrationFeatureKey, getFeatureDefinition } from "@/lib/vibration-features";
import type { HealthMetricTrend, HealthStatusLevel } from "@/types/health-status";
import type { FactorTrendSeries } from "@/types/factor-trends";

function mapFeatureStatus(status: string): HealthStatusLevel {
  const s = status.toLowerCase();
  if (s === "critical") return "danger";
  if (s === "warning") return "warning";
  if (s === "normal") return "healthy";
  return "neutral";
}

function formatUnit(unit: string): string {
  if (unit === "scaled_eng" || unit === "scaled") return "scaled";
  if (unit === "scaled_eng_sq" || unit === "scaled²") return "scaled²";
  if (unit === "dimensionless" || unit === "-") return "";
  return unit;
}

function toHealthMetricTrend(factor: FactorTrendSeries): HealthMetricTrend {
  const key = resolveVibrationFeatureKey(factor.feature_code);
  const def = key ? getFeatureDefinition(key) : null;
  const unit = formatUnit(factor.unit || def?.unit || "");

  return {
    key: (key ?? factor.feature_code) as HealthMetricTrend["key"],
    label: `${factor.feature_name} Trend`,
    unit,
    value: factor.value,
    trendX: factor.trend_x,
    trendY: factor.trend_y,
    available: factor.trend_y.length > 0,
    status: mapFeatureStatus(factor.status),
  };
}

interface UseUploadFactorTrendsOptions {
  uploadId: string;
  channel: number;
  enabled?: boolean;
}

export function useUploadFactorTrends({
  uploadId,
  channel,
  enabled = true,
}: UseUploadFactorTrendsOptions) {
  const query = useQuery({
    queryKey: ["upload-factor-trends", uploadId, channel],
    queryFn: () => getUploadFactorTrends(uploadId, channel),
    enabled: enabled && !!uploadId,
    retry: 2,
    staleTime: 30_000,
    gcTime: 300_000,
    refetchOnMount: "always",
    refetchInterval: (q) => {
      const status = q.state.data?.features_status;
      if (status && status !== "ready" && status !== "failed") {
        return 3000;
      }
      return false;
    },
  });

  const trendMetrics = useMemo(
    () => (query.data?.factors ?? []).map(toHealthMetricTrend),
    [query.data]
  );

  const featuresStatus =
    query.data?.features_status ??
    (query.isPending || query.isFetching ? "computing" : "pending");

  return {
    ...query,
    trendMetrics,
    featuresStatus,
    hasTrendData: trendMetrics.length > 0,
  };
}
