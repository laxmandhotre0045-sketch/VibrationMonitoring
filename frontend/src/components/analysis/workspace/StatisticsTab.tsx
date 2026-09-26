import React, { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { getUploadFeatures } from "@/api/measurements";
import { formatHealthMetricDisplay } from "@/lib/health-trend-option";
import { getFeatureDefinition, type VibrationFeatureKey } from "@/lib/vibration-features";
import { analysisBodyStack } from "@/components/analysis/analysis-layout";
import { cn } from "@/lib/utils";

/**
 * The statistical summary, in the order a reader expects it.
 *
 * Every one of these is computed by the backend and read from the features
 * endpoint. This tab used to recompute RMS, peak, crest, skew and kurtosis from
 * the plotted waveform, which meant a number on screen could have come from
 * either side and no finding could be traced to one source. The browser no
 * longer has an opinion: if the API has not computed a feature, the row says
 * so rather than filling itself in.
 */
const SUMMARY_KEYS: VibrationFeatureKey[] = [
  "rms",
  "peak",
  "peak_to_peak",
  "std_dev",
  "dc_offset",
  "crest_factor",
  "skewness",
  "kurtosis",
];

interface StatisticsTabProps {
  uploadId: string;
  samplingRateHz: number;
  activeChannel: number;
  plotsEnabled: boolean;
}

interface StatRow {
  parameter: string;
  value: string;
}

export function StatisticsTab({
  uploadId,
  samplingRateHz,
  activeChannel,
  plotsEnabled,
}: StatisticsTabProps) {
  const featuresQuery = useQuery({
    queryKey: ["upload-features", uploadId, activeChannel],
    queryFn: () => getUploadFeatures(uploadId, activeChannel),
    enabled: Boolean(uploadId) && plotsEnabled,
    staleTime: 60_000,
  });

  const rows = useMemo((): StatRow[] => {
    const items = featuresQuery.data?.items;
    if (!items?.length) return [];

    const byKey = new Map(
      items.filter((item) => item.feature_key).map((item) => [item.feature_key, item])
    );

    const measured: StatRow[] = SUMMARY_KEYS.map((key) => {
      const definition = getFeatureDefinition(key);
      const item = byKey.get(key);
      const value = typeof item?.value === "number" ? item.value : null;

      return {
        parameter: definition.label,
        // A feature the API did not return is absent, not zero. Printing a
        // number here would be the browser having an opinion again.
        value:
          value === null
            ? "—"
            : formatHealthMetricDisplay(value, definition.unit === "-" ? "" : definition.unit),
      };
    });

    // Configuration, not measurement: these describe how the capture was taken
    // rather than what was in it, so they are not features and never were.
    return [
      { parameter: "Channel", value: `ch${activeChannel}` },
      ...measured,
      { parameter: "Sampling Rate", value: `${samplingRateHz.toLocaleString()} Hz` },
    ];
  }, [featuresQuery.data, activeChannel, samplingRateHz]);

  return (
    <div className={analysisBodyStack}>
      <p className="text-sm text-muted-foreground">
        Statistical summary for the active diagnostic channel and selected capture, as computed
        by the analysis engine.
      </p>

      {!plotsEnabled && (
        <p className="text-sm text-muted-foreground">
          Select a capture on the timeline to view statistics.
        </p>
      )}

      {plotsEnabled && featuresQuery.isLoading && (
        <p className="text-sm text-muted-foreground">Loading statistics…</p>
      )}

      {plotsEnabled && featuresQuery.isError && (
        <p className="text-sm text-muted-foreground">
          Statistics are unavailable for channel ch{activeChannel}: the analysis engine could not
          be reached.
        </p>
      )}

      {plotsEnabled && !featuresQuery.isLoading && !featuresQuery.isError && rows.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No features have been computed for channel ch{activeChannel} on this capture.
        </p>
      )}

      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full min-w-[480px] text-sm">
            <thead>
              <tr className="border-b border-border bg-surface/60 text-left">
                <th className="px-3 py-2 font-semibold text-muted-foreground">Parameter</th>
                <th className="px-3 py-2 font-semibold text-muted-foreground">Value</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.parameter} className="border-b border-border last:border-b-0">
                  <td className="px-3 py-2 font-medium text-foreground">{row.parameter}</td>
                  <td className={cn("px-3 py-2 text-foreground font-semibold")}>{row.value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
