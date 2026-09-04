import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { compareUploadFeatures, getUploadFactorTrends, getUploadFeatures } from "@/api/measurements";
import { resolveVibrationFeatureKey, getFeatureDefinition } from "@/lib/vibration-features";
import {
  graphThresholdsToHealthMetric,
  resolveFeatureThresholdLines,
} from "@/lib/feature-threshold-lines";
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

interface BuildMetricContext {
  channelRms: number | null;
  baselineByCode: Record<string, number>;
  capturedAt: string | null;
}

function toHealthMetricTrend(
  factor: FactorTrendSeries,
  context: BuildMetricContext
): HealthMetricTrend {
  const key = resolveVibrationFeatureKey(factor.feature_code);
  const def = key ? getFeatureDefinition(key) : null;
  const unit = formatUnit(factor.unit || def?.unit || "");

  const baselineValue =
    context.baselineByCode[factor.feature_code] ??
    (key ? context.baselineByCode[key] : undefined) ??
    null;

  const thresholdLines = resolveFeatureThresholdLines(factor.feature_code, {
    channelRms: context.channelRms,
    baselineValue,
  });
  const thresholdFields = graphThresholdsToHealthMetric(thresholdLines);

  return {
    key: (key ?? factor.feature_code) as HealthMetricTrend["key"],
    label: `${factor.feature_name} Trend`,
    unit,
    value: factor.value,
    trendX: factor.trend_x,
    trendY: factor.trend_y,
    capturedAt: context.capturedAt,
    available: factor.trend_y.length > 0,
    status: mapFeatureStatus(factor.status),
    ...thresholdFields,
  };
}

interface UseUploadFactorTrendsOptions {
  uploadId: string;
  channel: number;
  baselineId?: string | null;
  enabled?: boolean;
}

export function useUploadFactorTrends({
  uploadId,
  channel,
  baselineId,
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

  const featuresQuery = useQuery({
    queryKey: ["upload-features-for-trends", uploadId, channel],
    queryFn: () => getUploadFeatures(uploadId, channel),
    enabled: enabled && !!uploadId,
    staleTime: 60_000,
  });

  const compareQuery = useQuery({
    queryKey: ["upload-features-compare-for-trends", uploadId, channel, baselineId],
    queryFn: () => compareUploadFeatures(uploadId, baselineId!, channel),
    enabled: enabled && !!uploadId && !!baselineId,
    staleTime: 60_000,
  });

  const trendMetrics = useMemo((): HealthMetricTrend[] => {
    const factors = query.data?.factors ?? [];
    if (factors.length === 0) return [];

    const channelRmsRaw =
      factors.find((f) => f.feature_code === "rms")?.value ??
      featuresQuery.data?.items.find((i) => i.feature_key === "rms")?.value;
    const channelRms = typeof channelRmsRaw === "number" ? channelRmsRaw : null;

    const baselineByCode: Record<string, number> = {};
    for (const item of compareQuery.data?.items ?? []) {
      if (item.baseline_value == null) continue;
      if (item.feature_key) {
        baselineByCode[item.feature_key] = item.baseline_value;
      }
      baselineByCode[item.feature] = item.baseline_value;
    }

    const context: BuildMetricContext = {
      channelRms,
      baselineByCode,
      capturedAt: query.data?.captured_at ?? null,
    };

    return factors.map((factor) => toHealthMetricTrend(factor, context));
  }, [query.data, featuresQuery.data, compareQuery.data]);

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
