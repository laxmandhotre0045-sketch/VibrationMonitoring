import React, { useState } from "react";
import type { Baseline } from "@/types/baseline";
import { analysisBodyStack } from "@/components/analysis/analysis-layout";
import { useFeatureHealthDashboard } from "@/hooks/useFeatureHealthDashboard";
import { HealthChannelSelector } from "./HealthChannelSelector";
import { HealthSummaryCards, HealthSummaryCardsSkeleton } from "./HealthSummaryCards";
import {
  ChannelHealthOverviewCard,
  ChannelHealthOverviewSkeleton,
} from "./ChannelHealthOverviewCard";
import { FeatureStatusTable, FeatureStatusTableSkeleton } from "./FeatureStatusTable";
import { FeatureThresholdLimitsSection } from "./FeatureThresholdLimitsSection";
import { FeatureComparisonSection } from "./FeatureComparisonSection";
import { FeatureTrendCardsSection } from "./FeatureTrendCardsSection";
import { HealthEmptyState } from "./HealthEmptyState";
import { cn } from "@/lib/utils";

interface StatusHealthTabProps {
  sensorId: string;
  selectedUploadId: string;
  channelCount: number;
  primaryBaseline?: Baseline | null;
  baselineList?: Baseline[];
}

export function StatusHealthTab({
  sensorId,
  selectedUploadId,
  channelCount,
  primaryBaseline,
  baselineList,
}: StatusHealthTabProps) {
  const [healthChannel, setHealthChannel] = useState(0);
  const enabled = !!sensorId && !!selectedUploadId;

  const dashboard = useFeatureHealthDashboard({
    sensorId,
    uploadId: selectedUploadId,
    channel: healthChannel,
    primaryBaseline,
    baselineList,
    enabled,
  });

  const {
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
    <div className={cn(analysisBodyStack, "space-y-g4")}>
      <HealthChannelSelector
        value={healthChannel}
        onChange={setHealthChannel}
        channelCount={channelCount}
        disabled={!enabled}
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

          <div className="space-y-g2">
            <h3 className="text-sm font-bold text-foreground">Feature Status Table</h3>
            {featureItems.length > 0 ? (
              <FeatureStatusTable items={featureItems} />
            ) : (
              <HealthEmptyState />
            )}
          </div>

          <FeatureThresholdLimitsSection
            uploadId={selectedUploadId}
            channel={healthChannel}
            channelLabel={channelLabel}
            baselineId={compareBaselineId || primaryBaseline?.id}
            enabled={enabled}
          />

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
        </>
      )}

      {enabled && (
        <FeatureTrendCardsSection
          uploadId={selectedUploadId}
          channel={healthChannel}
          channelLabel={channelLabel}
          baselineId={compareBaselineId || primaryBaseline?.id}
          enabled={enabled}
        />
      )}
    </div>
  );
}
