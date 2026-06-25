import React, { useState } from "react";
import type { Baseline } from "@/types/baseline";
import { analysisBodyStack, analysisGridGap } from "@/components/analysis/analysis-layout";
import { useFeatureHealthDashboard } from "@/hooks/useFeatureHealthDashboard";
import { HealthChannelSelector } from "./HealthChannelSelector";
import { HealthInfoBanner } from "./HealthInfoBanner";
import { HealthMetricCard } from "./HealthMetricCard";
import { SensorThresholdConfig } from "./SensorThresholdConfig";
import { HealthSummaryCards, HealthSummaryCardsSkeleton } from "./HealthSummaryCards";
import {
  ChannelHealthOverviewCard,
  ChannelHealthOverviewSkeleton,
} from "./ChannelHealthOverviewCard";
import { FeatureStatusTable, FeatureStatusTableSkeleton } from "./FeatureStatusTable";
import { FeatureComparisonSection } from "./FeatureComparisonSection";
import { HealthEmptyState } from "./HealthEmptyState";
import { cn } from "@/lib/utils";

interface StatusHealthTabProps {
  sensorId: string;
  selectedUploadId: string;
  samplingRateHz: number;
  primaryBaseline?: Baseline | null;
  baselineList?: Baseline[];
}

export function StatusHealthTab({
  sensorId,
  selectedUploadId,
  samplingRateHz,
  primaryBaseline,
  baselineList,
}: StatusHealthTabProps) {
  const [healthChannel, setHealthChannel] = useState(0);
  const enabled = !!sensorId && !!selectedUploadId;

  const dashboard = useFeatureHealthDashboard({
    sensorId,
    uploadId: selectedUploadId,
    channel: healthChannel,
    samplingRateHz,
    primaryBaseline,
    baselineList,
    enabled,
  });

  const {
    healthQuery,
    featureItems,
    compareItems,
    summary,
    channelOverview,
    compareBaselineId,
    setCompareBaselineId,
    baselineOptions,
    isLoading,
    hasFeatureData,
    hasFeatureTable,
  } = dashboard;

  const channelLabel = `CH-${healthChannel + 1}`;
  const featuresQueryError = dashboard.featuresQuery.error;

  return (
    <div className={cn(analysisBodyStack, "space-y-4")}>
      <HealthChannelSelector
        value={healthChannel}
        onChange={setHealthChannel}
        disabled={!enabled}
      />

      <HealthInfoBanner
        message={
          healthQuery.snapshot?.bannerMessage ??
          "No thresholds saved for this sensor/channel set. Showing calculated trend only."
        }
        hasThresholds={healthQuery.snapshot?.hasThresholds}
      />

      {!enabled && (
        <p className="text-sm text-muted-foreground">
          Select a sensor and timeline capture to load health status metrics.
        </p>
      )}

      {enabled && isLoading && (
        <>
          <HealthSummaryCardsSkeleton />
          <ChannelHealthOverviewSkeleton />
          <FeatureStatusTableSkeleton />
        </>
      )}

      {enabled && !isLoading && !hasFeatureData && !featuresQueryError && (
        <HealthEmptyState />
      )}

      {enabled && featuresQueryError && (
        <p className="text-sm text-destructive font-semibold">
          Unable to load feature data for {channelLabel}.
        </p>
      )}

      {enabled && (hasFeatureData || hasFeatureTable) && (
        <>
          <HealthSummaryCards summary={summary} />

          {channelOverview && (
            <ChannelHealthOverviewCard
              data={channelOverview}
              channelLabel={channelLabel}
            />
          )}

          <div className="space-y-2">
            <h3 className="text-sm font-bold text-foreground">Feature Status Table</h3>
            {featureItems.length > 0 ? (
              <FeatureStatusTable items={featureItems} />
            ) : (
              <HealthEmptyState />
            )}
          </div>

          <FeatureComparisonSection
            items={compareItems}
            baselineOptions={baselineOptions}
            selectedBaselineId={compareBaselineId}
            onBaselineChange={setCompareBaselineId}
            isLoading={dashboard.compareIsLoading}
            error={dashboard.compareHasApiError ? dashboard.compareQuery.error : null}
            onRetry={() => {
              void dashboard.compareQuery.refetch();
            }}
          />

          <SensorThresholdConfig
            channelLabel={channelLabel}
            hasThresholds={healthQuery.snapshot?.hasThresholds ?? false}
            cautionThreshold={healthQuery.snapshot?.cautionThreshold}
            warningThreshold={healthQuery.snapshot?.warningThreshold}
          />

          {healthQuery.snapshot && healthQuery.snapshot.statusCardMetrics.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-sm font-bold text-foreground">Feature Trend Monitoring</h3>
              <div className={cn("grid grid-cols-1 md:grid-cols-2", analysisGridGap)}>
                {healthQuery.snapshot.statusCardMetrics.map((metric) => (
                  <HealthMetricCard
                    key={`${healthChannel}-${metric.key}`}
                    metric={metric}
                    channelLabel={channelLabel}
                    onRefresh={() => healthQuery.refetch()}
                    isRefreshing={healthQuery.isFetching}
                  />
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
