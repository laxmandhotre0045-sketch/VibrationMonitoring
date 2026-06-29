import React from "react";
import type { ChartStatistics } from "@/lib/chart-statistics";
import { formatStatValue } from "@/lib/chart-statistics";
import { cn } from "@/lib/utils";

interface GraphStatisticsPanelProps {
  stats: ChartStatistics;
  className?: string;
}

const STAT_ITEMS: {
  key: keyof ChartStatistics;
  label: string;
  format?: (value: ChartStatistics[keyof ChartStatistics]) => string;
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

export function GraphStatisticsPanel({ stats, className }: GraphStatisticsPanelProps) {
  return (
    <div
      className={cn(
        "grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-10 gap-2",
        "rounded-lg border border-border bg-[#FAFAF8] px-3 py-2.5",
        className
      )}
    >
      {STAT_ITEMS.map((item) => {
        const raw = stats[item.key];
        const display =
          item.format?.(raw) ??
          (typeof raw === "number" ? formatStatValue(raw) : String(raw ?? "—"));

        return (
          <div key={item.key} className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground truncate">
              {item.label}
            </p>
            <p className="mt-0.5 text-sm font-bold text-foreground tabular-nums truncate">
              {display}
            </p>
          </div>
        );
      })}
    </div>
  );
}
