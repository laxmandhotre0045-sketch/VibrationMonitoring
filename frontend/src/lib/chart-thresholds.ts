import type { PlotSeries } from "@/types/measurements";
import { ECHARTS_BRAND } from "./echarts-theme";

export interface PlotThresholds {
  warning?: number;
  danger?: number;
}

function readThreshold(metadata: Record<string, unknown>, key: string): number | undefined {
  const value = metadata[key];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

export function getPlotThresholds(plot: PlotSeries): PlotThresholds {
  return {
    warning: readThreshold(plot.metadata, "warning_threshold"),
    danger: readThreshold(plot.metadata, "danger_threshold"),
  };
}

export function thresholdValues(thresholds: PlotThresholds): number[] {
  return [thresholds.warning, thresholds.danger].filter(
    (value): value is number => value !== undefined
  );
}

type ThresholdMarkLineDatum = {
  yAxis: number;
  name: string;
  lineStyle: { color: string; type: "dashed" | "dotted"; width: number };
  label: { show: boolean };
};

/** Horizontal threshold markLines for ECharts — fixed Y during X zoom. */
export function buildEchartsThresholdMarkLines(
  thresholds: PlotThresholds
): ThresholdMarkLineDatum[] {
  const data: ThresholdMarkLineDatum[] = [];

  if (thresholds.warning !== undefined) {
    data.push({
      yAxis: thresholds.warning,
      name: "Warning",
      lineStyle: { color: ECHARTS_BRAND.amber, type: "dashed", width: 1.5 },
      label: { show: false },
    });
  }

  if (thresholds.danger !== undefined) {
    data.push({
      yAxis: thresholds.danger,
      name: "Danger",
      lineStyle: { color: ECHARTS_BRAND.orange, type: "dotted", width: 1.5 },
      label: { show: false },
    });
  }

  return data;
}

export function echartsThresholdMarkLineConfig(thresholds: PlotThresholds) {
  const data = buildEchartsThresholdMarkLines(thresholds);
  if (data.length === 0) return undefined;
  return {
    symbol: ["none", "none"],
    silent: true,
    data,
  };
}
