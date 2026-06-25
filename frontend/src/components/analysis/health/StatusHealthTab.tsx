import React, { useState } from "react";
import { analysisBodyStack, analysisGridGap } from "@/components/analysis/analysis-layout";
import { useHealthStatusData } from "@/hooks/useHealthStatusData";
import { HealthChannelSelector } from "./HealthChannelSelector";
import { HealthInfoBanner } from "./HealthInfoBanner";
import { HealthMetricCard } from "./HealthMetricCard";
import { HealthThresholdsTable } from "./HealthThresholdsTable";
import { SensorThresholdConfig } from "./SensorThresholdConfig";
import { cn } from "@/lib/utils";

interface StatusHealthTabProps {
  sensorId: string;
  selectedUploadId: string;
  samplingRateHz: number;
}

export function StatusHealthTab({
  sensorId,
  selectedUploadId,
  samplingRateHz,
}: StatusHealthTabProps) {
  const [healthChannel, setHealthChannel] = useState(0);
  const enabled = !!sensorId && !!selectedUploadId;

  const { snapshot, isLoading, isFetching, error, refetch } = useHealthStatusData({
    uploadId: selectedUploadId,
    channel: healthChannel,
    samplingRateHz,
    enabled,
  });

  return (
    <div className={analysisBodyStack}>
      <HealthChannelSelector
        value={healthChannel}
        onChange={setHealthChannel}
        disabled={!enabled}
      />

      <HealthInfoBanner
        message={
          snapshot?.bannerMessage ??
          "No thresholds saved for this sensor/channel set. Showing calculated trend only."
        }
        hasThresholds={snapshot?.hasThresholds}
      />

      {!enabled && (
        <p className="text-sm text-muted-foreground">
          Select a sensor and timeline capture to load health status metrics.
        </p>
      )}

      {enabled && isLoading && (
        <p className="text-sm text-muted-foreground">Loading health metrics…</p>
      )}

      {enabled && error && (
        <p className="text-sm text-destructive font-semibold">
          Failed to load health data for {snapshot?.channelLabel ?? `CH-${healthChannel + 1}`}.
        </p>
      )}

      {enabled && snapshot && snapshot.statusCardMetrics.length > 0 && (
        <>
          <div className={cn("grid grid-cols-1 md:grid-cols-2", analysisGridGap)}>
            {snapshot.statusCardMetrics.map((metric) => (
              <HealthMetricCard
                key={`${healthChannel}-${metric.key}`}
                metric={metric}
                channelLabel={snapshot.channelLabel}
                onRefresh={() => refetch()}
                isRefreshing={isFetching}
              />
            ))}
          </div>

          <div className="space-y-2">
            <h3 className="text-sm font-bold text-foreground">Details &amp; Thresholds</h3>
            <HealthThresholdsTable rows={snapshot.thresholdRows} />
          </div>

          <SensorThresholdConfig
            channelLabel={snapshot.channelLabel}
            hasThresholds={snapshot.hasThresholds}
            cautionThreshold={snapshot.cautionThreshold}
            warningThreshold={snapshot.warningThreshold}
          />
        </>
      )}

      {enabled && !isLoading && snapshot && snapshot.statusCardMetrics.length === 0 && !error && (
        <p className="text-sm text-muted-foreground">
          No waveform data available for {snapshot.channelLabel}. Select another channel or capture.
        </p>
      )}
    </div>
  );
}
