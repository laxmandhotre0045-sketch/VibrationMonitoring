import React, { useState } from "react";
import { HeartPulse } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";
import { AnalysisSectionHeader } from "@/components/analysis/AnalysisSectionHeader";
import {
  analysisBodyStack,
  analysisCardPad,
  analysisGridGap,
} from "@/components/analysis/analysis-layout";
import { useHealthStatusData } from "@/hooks/useHealthStatusData";
import { HealthChannelSelector } from "./HealthChannelSelector";
import { HealthInfoBanner } from "./HealthInfoBanner";
import { HealthMetricCard } from "./HealthMetricCard";
import { cn } from "@/lib/utils";

interface StatusHealthSectionProps {
  sensorId: string;
  selectedUploadId: string;
  samplingRateHz: number;
}

export function StatusHealthSection({
  sensorId,
  selectedUploadId,
  samplingRateHz,
}: StatusHealthSectionProps) {
  const [healthChannel, setHealthChannel] = useState(0);
  const enabled = !!sensorId && !!selectedUploadId;

  const {
    snapshot,
    isLoading,
    isFetching,
    error,
    refetch,
  } = useHealthStatusData({
    uploadId: selectedUploadId,
    channel: healthChannel,
    samplingRateHz,
    enabled,
  });

  const handleChannelChange = (channel: number) => {
    setHealthChannel(channel);
  };

  return (
    <GlassCard className={analysisCardPad} delay={0.15}>
      <AnalysisSectionHeader
        icon={HeartPulse}
        title="Status (Health)"
        subtitle="Channel-based health indicators and calculated segment trends for the selected capture."
      />

      <div className={analysisBodyStack}>
        <HealthChannelSelector
          value={healthChannel}
          onChange={handleChannelChange}
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

        {enabled && snapshot && snapshot.metrics.length > 0 && (
          <div className={cn("grid grid-cols-1 md:grid-cols-2", analysisGridGap)}>
            {snapshot.metrics.map((metric) => (
              <HealthMetricCard
                key={`${healthChannel}-${metric.key}`}
                metric={metric}
                channelLabel={snapshot.channelLabel}
              />
            ))}
          </div>
        )}

        {enabled && !isLoading && snapshot && snapshot.metrics.length === 0 && !error && (
          <p className="text-sm text-muted-foreground">
            No waveform data available for {snapshot.channelLabel}. Select another channel or capture.
          </p>
        )}
      </div>
    </GlassCard>
  );
}
