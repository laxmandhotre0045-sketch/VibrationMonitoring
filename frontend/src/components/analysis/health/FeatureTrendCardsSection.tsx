import React, { useMemo } from "react";
import { RefreshCw } from "lucide-react";
import { HealthMetricCard } from "@/components/analysis/health/HealthMetricCard";
import { analysisGridGap } from "@/components/analysis/analysis-layout";
import { useUploadFactorTrends } from "@/hooks/useUploadFactorTrends";
import type { HealthMetricTrend } from "@/types/health-status";
import { cn } from "@/lib/utils";

interface FeatureTrendCardsSectionProps {
  uploadId: string;
  channel: number;
  channelLabel: string;
  baselineId?: string | null;
  enabled: boolean;
  className?: string;
}

/**
 * Reading order for the KPI grid — pure presentation, applied on top of
 * whatever order the factor-trends response arrives in.
 *
 * Two columns wide, it pairs each metric with the one an analyst reads it
 * against: RMS beside Peak (level vs. worst excursion), Kurtosis beside Crest
 * Factor (both impulsiveness), then the harmonics in 1X/2X/3X order, and the
 * two derived floors last. Any key not listed keeps its API order behind these.
 */
const KPI_DISPLAY_ORDER = [
  "rms",
  "peak",
  "kurtosis",
  "crest_factor",
  "fft_band_energy",
  "amplitude_1x",
  "amplitude_2x",
  "amplitude_3x",
  "envelope_rms",
  "noise_floor",
];

function orderIndex(metric: HealthMetricTrend): number {
  const index = KPI_DISPLAY_ORDER.indexOf(metric.key);
  return index === -1 ? KPI_DISPLAY_ORDER.length : index;
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

  const orderedMetrics = useMemo(() => {
    // Stable: equal keys keep their arrival order, so an unlisted feature never
    // jumps around between renders.
    return trendMetrics
      .map((metric, index) => ({ metric, index }))
      .sort((a, b) => orderIndex(a.metric) - orderIndex(b.metric) || a.index - b.index)
      .map((entry) => entry.metric);
  }, [trendMetrics]);

  const isComputing =
    enabled &&
    !hasTrendData &&
    (isPending || isLoading || isFetching || featuresStatus === "computing");

  return (
    <section className={cn("space-y-g3", className)}>
      <div className="flex flex-wrap items-end justify-between gap-g2">
        <div className="min-w-0">
          <h3 className="text-sm font-bold text-foreground">Feature Trend Monitoring</h3>
          <p className="mt-g1 text-sm text-muted-foreground">
            Segment trends for all 10 vibration features within the selected capture.
          </p>
        </div>
        {hasTrendData && (
          <div className="flex shrink-0 items-center gap-g2">
            <span className="inline-flex items-center gap-1.5 rounded-md border border-border bg-white px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
              {channelLabel}
              <span className="text-border" aria-hidden>
                |
              </span>
              {orderedMetrics.length} features
            </span>
            {/* One refresh for the whole grid — every card reads the same
                query, so ten per-card buttons all fired this same refetch. */}
            <button
              type="button"
              title="Refresh feature trends"
              onClick={() => void refetch()}
              disabled={isFetching}
              className={cn(
                "inline-flex h-8 w-8 items-center justify-center rounded-md border border-border bg-white",
                "text-muted-foreground transition-colors hover:bg-warm hover:text-foreground",
                "disabled:cursor-not-allowed disabled:opacity-40"
              )}
            >
              <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
            </button>
          </div>
        )}
      </div>

      {enabled && isComputing && (
        <p className="text-sm text-muted-foreground">
          Computing feature trends for this capture (first load may take a few seconds)…
        </p>
      )}

      {enabled && isError && (
        <p className="text-sm text-destructive font-semibold">
          {(error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
            "Unable to load feature trends. Re-upload the capture if features were not computed."}
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
        // Two columns only once there is real width for them: at `md` a 300px
        // plot in half a tablet is narrower than its own axis labels.
        <div className={cn("grid grid-cols-1 lg:grid-cols-2 items-stretch", analysisGridGap)}>
          {orderedMetrics.map((metric) => (
            <HealthMetricCard
              key={`factor-trend-${channel}-${metric.key}`}
              metric={metric}
              channelLabel={channelLabel}
            />
          ))}
        </div>
      )}
    </section>
  );
}
