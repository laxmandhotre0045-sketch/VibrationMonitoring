import type { Layout } from "plotly.js";
import type { PlotSeries } from "@/types/measurements";
import { PLOTLY_BRAND } from "./plotly-theme";

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

/** Horizontal threshold lines at fixed Y values; span the visible plot width during X zoom. */
export function createThresholdShapes(thresholds: PlotThresholds): Partial<Layout["shapes"][number]>[] {
  const shapes: Partial<Layout["shapes"][number]>[] = [];

  if (thresholds.warning !== undefined) {
    shapes.push({
      type: "line",
      xref: "paper",
      x0: 0,
      x1: 1,
      yref: "y",
      y0: thresholds.warning,
      y1: thresholds.warning,
      line: { color: PLOTLY_BRAND.amber, width: 1.5, dash: "dash" },
    });
  }

  if (thresholds.danger !== undefined) {
    shapes.push({
      type: "line",
      xref: "paper",
      x0: 0,
      x1: 1,
      yref: "y",
      y0: thresholds.danger,
      y1: thresholds.danger,
      line: { color: PLOTLY_BRAND.orange, width: 1.5, dash: "dot" },
    });
  }

  return shapes;
}
