import React from "react";
import type { ChartStatistics } from "@/lib/chart-statistics";
import { formatStatValue } from "@/lib/chart-statistics";
import { cn } from "@/lib/utils";

interface GraphStatisticsPanelProps {
  stats: ChartStatistics;
  amplitudeUnit?: string;
  className?: string;
}

const PRIMARY_STATS: Array<keyof ChartStatistics> = ["rms", "peak", "peakToPeak", "crestFactor"];

const STAT_ITEMS: {
  key: keyof ChartStatistics;
  label: string;
  format?: (value: ChartStatistics[keyof ChartStatistics], unit?: string) => string;
}[] = [
  { key: "rms", label: "RMS" },
  { key: "peak", label: "Peak" },
  { key: "peakToPeak", label: "Peak-to-Peak" },
  { key: "mean", label: "Mean" },
  { key: "min", label: "Min" },
  { key: "max", label: "Max" },
  { key: "crestFactor", label: "Crest Factor" },
  {
    key: "samplingRateHz",
    label: "Sampling Rate",
    format: (v) => (typeof v === "number" ? `${v.toLocaleString()} Hz` : "—"),
  },
  {
    key: "rpm",
    label: "RPM",
    format: (v) => (typeof v === "number" ? v.toFixed(1) : "—"),
  },
  {
    key: "sensorStatus",
    label: "Sensor Status",
    format: (v) => String(v ?? "—"),
  },
];

export function GraphStatisticsPanel({
  stats,
  amplitudeUnit,
  className,
}: GraphStatisticsPanelProps) {
  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-[#FAFAF8] px-3 py-2.5 space-y-2",
        className
      )}
    >
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-10 gap-2">
        {STAT_ITEMS.map((item) => {
          const raw = stats[item.key];
          const isAmplitudeStat = ["rms", "peak", "peakToPeak", "mean", "min", "max"].includes(
            item.key
          );
          const unit = isAmplitudeStat ? amplitudeUnit : undefined;
          const display =
            item.format?.(raw, unit) ??
            (typeof raw === "number" ? formatStatValue(raw, 4, unit) : String(raw ?? "—"));
          const isPrimary = PRIMARY_STATS.includes(item.key);

          return (
            <div
              key={item.key}
              className={cn(
                "min-w-0 rounded-md px-1.5 py-1",
                isPrimary && "bg-white/80 ring-1 ring-signal-light/25"
              )}
            >
              <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground truncate">
                {item.label}
              </p>
              <p
                className={cn(
                  "mt-0.5 font-bold text-foreground tabular-nums truncate",
                  isPrimary ? "text-sm" : "text-xs"
                )}
              >
                {display}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
