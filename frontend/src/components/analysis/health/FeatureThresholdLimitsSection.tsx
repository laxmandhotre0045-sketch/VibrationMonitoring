import React, { useMemo } from "react";
import { HealthThresholdsTable } from "@/components/analysis/health/HealthThresholdsTable";
import { buildThresholdRows } from "@/lib/health-metrics";
import { useUploadFactorTrends } from "@/hooks/useUploadFactorTrends";
import type { HealthMetricTrend } from "@/types/health-status";
import { cn } from "@/lib/utils";

interface FeatureThresholdLimitsSectionProps {
  uploadId: string;
  channel: number;
  channelLabel: string;
  baselineId?: string | null;
  enabled: boolean;
  className?: string;
}

/**
 * Shows each feature's latest value alongside the limits that judged it.
 *
 * The Feature Status Table above this one reports the verdict (Normal / Caution /
 * Warning) without the numbers behind it, so a reading sitting just under its
 * limit looks identical to one with plenty of headroom. This section fills that
 * gap: caution and warning limits, the move since the prior segment, and the
 * range across the capture.
 *
 * It reuses the factor-trend query that FeatureTrendCardsSection already runs —
 * same key, so React Query serves both from one fetch — because the trend series
 * is what carries the resolved threshold lines and the per-segment history.
 */
export function FeatureThresholdLimitsSection({
  uploadId,
  channel,
  channelLabel,
  baselineId,
  enabled,
  className,
}: FeatureThresholdLimitsSectionProps) {
  const { trendMetrics, isError, featuresStatus, isPending, isLoading, isFetching, hasTrendData } =
    useUploadFactorTrends({ uploadId, channel, baselineId, enabled });

  const rows = useMemo(() => {
    // The trend cards label every series "<Feature> Trend"; in a limits table the
    // suffix is noise, and buildThresholdRows folds the unit in after the label.
    const named: HealthMetricTrend[] = trendMetrics.map((metric) => ({
      ...metric,
      label: metric.label.replace(/\s+Trend$/, ""),
    }));
    return buildThresholdRows(named);
  }, [trendMetrics]);

  const isComputing =
    enabled &&
    !hasTrendData &&
    (isPending || isLoading || isFetching || featuresStatus === "computing");

  return (
    <section className={cn("space-y-g3", className)}>
      <div>
        <h3 className="text-sm font-bold text-foreground">Threshold Limits</h3>
        <p className="mt-g1 text-sm text-muted-foreground">
          Latest reading for {channelLabel} against its caution and warning limits.
        </p>
      </div>

      {isComputing && (
        <div className="rounded-md border border-border bg-white p-3 space-y-g2 animate-pulse">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-8 rounded-md bg-muted/40" />
          ))}
        </div>
      )}

      {!isComputing && isError && (
        <p className="text-sm text-destructive font-semibold">
          Unable to load threshold limits for {channelLabel}.
        </p>
      )}

      {!isComputing && !isError && <HealthThresholdsTable rows={rows} />}
    </section>
  );
}
