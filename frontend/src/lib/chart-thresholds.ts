import type { PlotSeries } from "@/types/measurements";
import type { GraphThresholdSet, ThresholdOverlayOptions } from "./threshold-overlay";
import {
  buildThresholdMarkLineConfig,
  resolveGraphThresholds,
  thresholdValuesFromSet,
} from "./threshold-overlay";

/** @deprecated Use GraphThresholdSet from threshold-overlay */
export interface PlotThresholds {
  warning?: number;
  danger?: number;
}

export function getPlotThresholds(plot: PlotSeries): PlotThresholds {
  const set = resolveGraphThresholds(plot);
  return {
    warning: set.warning,
    danger: set.critical,
  };
}

export function thresholdValues(thresholds: PlotThresholds): number[] {
  return [thresholds.warning, thresholds.danger].filter(
    (value): value is number => value !== undefined
  );
}

export function plotThresholdsFromSet(set: GraphThresholdSet): PlotThresholds {
  return { warning: set.warning, danger: set.critical };
}

/** @deprecated Use buildThresholdMarkLineConfig */
export function echartsThresholdMarkLineConfig(
  thresholds: PlotThresholds,
  options?: ThresholdOverlayOptions
) {
  const set: GraphThresholdSet = {
    warning: thresholds.warning,
    critical: thresholds.danger,
  };
  return buildThresholdMarkLineConfig(set, options);
}

export function echartsThresholdValues(
  plot: PlotSeries,
  options?: ThresholdOverlayOptions
): number[] {
  const set = options?.thresholds ?? resolveGraphThresholds(plot);
  return thresholdValuesFromSet(set);
}
