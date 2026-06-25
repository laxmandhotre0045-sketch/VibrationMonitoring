import React, { useMemo } from "react";
import type { PlotSeries } from "@/types/measurements";
import {
  crestFactor,
  kurtosisExcess,
  peak,
  rms,
  skewness,
} from "@/lib/health-metrics";
import { formatHealthMetricDisplay } from "@/lib/health-trend-option";
import { analysisBodyStack } from "@/components/analysis/analysis-layout";
import { cn } from "@/lib/utils";

interface StatisticsTabProps {
  plotsData: { plots: PlotSeries[] } | undefined;
  samplingRateHz: number;
  activeChannel: number;
  plotsEnabled: boolean;
  plotsLoading: boolean;
}

interface StatRow {
  parameter: string;
  value: string;
}

export function StatisticsTab({
  plotsData,
  samplingRateHz,
  activeChannel,
  plotsEnabled,
  plotsLoading,
}: StatisticsTabProps) {
  const rows = useMemo((): StatRow[] => {
    const waveform = plotsData?.plots.find((p) => p.plot_type === "time_waveform");
    if (!waveform || waveform.y.length === 0) return [];

    const samples = waveform.y;
    const mean =
      samples.reduce((sum, v) => sum + v, 0) / samples.length;
    const variance =
      samples.reduce((sum, v) => sum + (v - mean) ** 2, 0) / samples.length;
    const stdDev = Math.sqrt(variance);
    const min = Math.min(...samples);
    const max = Math.max(...samples);

    return [
      { parameter: "Channel", value: `ch${activeChannel}` },
      { parameter: "Sample Count", value: samples.length.toLocaleString() },
      { parameter: "Mean", value: formatHealthMetricDisplay(mean, "g") },
      { parameter: "Std Dev", value: formatHealthMetricDisplay(stdDev, "g") },
      { parameter: "Min", value: formatHealthMetricDisplay(min, "g") },
      { parameter: "Max", value: formatHealthMetricDisplay(max, "g") },
      { parameter: "RMS", value: formatHealthMetricDisplay(rms(samples), "g") },
      { parameter: "Peak", value: formatHealthMetricDisplay(peak(samples), "g") },
      { parameter: "Crest Factor", value: formatHealthMetricDisplay(crestFactor(samples), "") },
      { parameter: "Skew", value: formatHealthMetricDisplay(skewness(samples), "") },
      { parameter: "Kurtosis", value: formatHealthMetricDisplay(kurtosisExcess(samples), "") },
      { parameter: "Sampling Rate", value: `${samplingRateHz.toLocaleString()} Hz` },
    ];
  }, [plotsData, activeChannel, samplingRateHz]);

  return (
    <div className={analysisBodyStack}>
      <p className="text-sm text-muted-foreground">
        Statistical summary for the active diagnostic channel and selected capture.
      </p>

      {!plotsEnabled && !plotsLoading && (
        <p className="text-sm text-muted-foreground">
          Select a capture on the timeline to view statistics.
        </p>
      )}

      {plotsLoading && (
        <p className="text-sm text-muted-foreground">Loading statistics…</p>
      )}

      {plotsEnabled && !plotsLoading && rows.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No waveform data available for statistics on channel ch{activeChannel}.
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
