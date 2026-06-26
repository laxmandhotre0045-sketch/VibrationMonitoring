import React from "react";
import { HealthChannelSelector } from "@/components/analysis/health/HealthChannelSelector";
import { HealthMetricCard } from "@/components/analysis/health/HealthMetricCard";
import { analysisBodyStack, analysisGridGap } from "@/components/analysis/analysis-layout";
import { useUploadFactorTrends } from "@/hooks/useUploadFactorTrends";
import { cn } from "@/lib/utils";

interface TrendAnalysisTabProps {
  selectedUploadId: string;
  channel: number;
  channelCount: number;
  onChannelChange: (channel: number) => void;
}

export function TrendAnalysisTab({
  selectedUploadId,
  channel,
  channelCount,
  onChannelChange,
}: TrendAnalysisTabProps) {
  const enabled = !!selectedUploadId;

  const { trendMetrics, isLoading, isError, error, featuresStatus, refetch, isFetching, isPending, hasTrendData } =
    useUploadFactorTrends({
      uploadId: selectedUploadId,
      channel,
      enabled,
    });

  const isComputing =
    enabled &&
    !hasTrendData &&
    (isPending || isLoading || isFetching || featuresStatus === "computing");

  return (
    <div className={analysisBodyStack}>
      <p className="text-sm text-muted-foreground">
        Factor trends for the selected capture — 10 features computed on upload (segment trends within
        the file). Values are in scaled engineering units from CSV.
      </p>

      <HealthChannelSelector
        value={channel}
        onChange={onChannelChange}
        channelCount={channelCount}
        disabled={!enabled}
      />

      {!enabled && (
        <p className="text-sm text-muted-foreground">
          Select a capture on the timeline to view factor trends.
        </p>
      )}

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

      {enabled && !isComputing && !isError && !hasTrendData && featuresStatus !== "ready" && featuresStatus !== "failed" && (
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
              channelLabel={`CH-${channel + 1}`}
              onRefresh={() => refetch()}
              isRefreshing={isFetching}
              trendFooterLabel="Factor trend"
            />
          ))}
        </div>
      )}
    </div>
  );
}
