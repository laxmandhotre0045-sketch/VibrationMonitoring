import React from "react";
import { HealthMetricCard } from "@/components/analysis/health/HealthMetricCard";
import { analysisGridGap } from "@/components/analysis/analysis-layout";
import { useUploadFactorTrends } from "@/hooks/useUploadFactorTrends";
import { cn } from "@/lib/utils";

interface FeatureTrendCardsSectionProps {
  uploadId: string;
  channel: number;
  channelLabel: string;
  baselineId?: string | null;
  enabled: boolean;
  className?: string;
}

export function FeatureTrendCardsSection({
  uploadId,
  channel,
  channelLabel,
  baselineId,
  enabled,
  className,
}: FeatureTrendCardsSectionProps) {
  const {
    trendMetrics,
    isLoading,
    isError,
    error,
    featuresStatus,
    refetch,
    isFetching,
    isPending,
    hasTrendData,
  } = useUploadFactorTrends({
    uploadId,
    channel,
    baselineId,
    enabled,
  });

  const isComputing =
    enabled &&
    !hasTrendData &&
    (isPending || isLoading || isFetching || featuresStatus === "computing");

  return (
    <section className={cn("space-y-3", className)}>
      <div>
        <h3 className="text-sm font-bold text-foreground">Feature Trend Monitoring</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Segment trends for all 10 vibration features within the selected capture.
        </p>
      </div>

      {enabled && isComputing && (
        <p className="text-sm text-muted-foreground">
          Computing factor trends for this capture (first load may take a few seconds)…
        </p>
      )}

      {enabled && isError && (
        <p className="text-sm text-destructive font-semibold">
          {(error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
            "Failed to load factor trends. Re-upload the file if features were not computed."}
        </p>
      )}

      {enabled && !isComputing && !isError && !hasTrendData && featuresStatus === "failed" && (
        <p className="text-sm text-destructive font-semibold">
          Feature computation failed for this capture. Re-upload the file to try again.
        </p>
      )}

      {enabled &&
        !isComputing &&
        !isError &&
        !hasTrendData &&
        featuresStatus !== "ready" &&
        featuresStatus !== "failed" && (
          <p className="text-sm text-signal-dark font-medium">
            Computing features… (status: {featuresStatus})
          </p>
        )}

      {enabled && !isComputing && !isError && hasTrendData && (
        <div className={cn("grid grid-cols-1 md:grid-cols-2", analysisGridGap)}>
          {trendMetrics.map((metric) => (
            <HealthMetricCard
              key={`factor-trend-${channel}-${metric.key}`}
              metric={metric}
              channelLabel={channelLabel}
              onRefresh={() => refetch()}
              isRefreshing={isFetching}
              trendFooterLabel="Factor trend"
            />
          ))}
        </div>
      )}
    </section>
  );
}
