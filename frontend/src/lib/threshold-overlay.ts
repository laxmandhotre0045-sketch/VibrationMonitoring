import type { PlotSeries } from "@/types/measurements";

export type ThresholdLevel = "normal" | "warning" | "critical";

export interface GraphThresholdSet {
  normal?: number;
  warning?: number;
  critical?: number;
}

export interface ThresholdOverlayOptions {
  showThresholds?: boolean;
  showShading?: boolean;
  showCrossings?: boolean;
  thresholds?: GraphThresholdSet;
}

export interface SeriesPoint {
  x: number;
  y: number;
}

export const THRESHOLD_LEVEL_ORDER: ThresholdLevel[] = ["normal", "warning", "critical"];

export const THRESHOLD_LEVEL_META: Record<
  ThresholdLevel,
  {
    label: string;
    color: string;
    shadeColor: string;
    lineType: "solid" | "dashed" | "dotted";
    crossingColor: string;
  }
> = {
  normal: {
    label: "Normal Threshold",
    color: "#2E7D32",
    shadeColor: "rgba(46, 125, 50, 0.06)",
    lineType: "solid",
    crossingColor: "#2E7D32",
  },
  warning: {
    label: "Warning Threshold",
    color: "#D98C00",
    shadeColor: "rgba(217, 140, 0, 0.10)",
    lineType: "dashed",
    crossingColor: "#D98C00",
  },
  critical: {
    label: "Critical Threshold",
    color: "#DC2626",
    shadeColor: "rgba(220, 38, 38, 0.12)",
    lineType: "dotted",
    crossingColor: "#DC2626",
  },
};

function readMetaNumber(metadata: Record<string, unknown>, keys: string[]): number | undefined {
  for (const key of keys) {
    const value = metadata[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
  }
  return undefined;
}

export function resolveGraphThresholds(
  plot?: PlotSeries,
  override?: GraphThresholdSet
): GraphThresholdSet {
  const metadata = (plot?.metadata ?? {}) as Record<string, unknown>;
  const resolved: GraphThresholdSet = {
    normal: readMetaNumber(metadata, ["normal_threshold", "healthy_threshold"]),
    warning: readMetaNumber(metadata, [
      "warning_threshold",
      "caution_threshold",
      "caution_limit",
    ]),
    critical: readMetaNumber(metadata, [
      "danger_threshold",
      "critical_threshold",
      "alarm_threshold",
      "warning_limit",
    ]),
  };

  if (override) {
    return {
      normal: override.normal ?? resolved.normal,
      warning: override.warning ?? resolved.warning,
      critical: override.critical ?? resolved.critical,
    };
  }
  return resolved;
}

export function resolveGraphThresholdsFromHealth(
  warningThreshold?: number,
  dangerThreshold?: number,
  normalThreshold?: number
): GraphThresholdSet {
  return {
    normal: normalThreshold,
    warning: warningThreshold,
    critical: dangerThreshold,
  };
}

export function hasConfiguredThresholds(thresholds: GraphThresholdSet): boolean {
  return (
    thresholds.normal !== undefined ||
    thresholds.warning !== undefined ||
    thresholds.critical !== undefined
  );
}

export function thresholdValuesFromSet(thresholds: GraphThresholdSet): number[] {
  return THRESHOLD_LEVEL_ORDER.map((level) => thresholds[level]).filter(
    (value): value is number => value !== undefined
  );
}

export function extractSeriesPoints(
  seriesData: Array<[number, number]> | number[],
  xValues?: number[]
): SeriesPoint[] {
  if (seriesData.length === 0) return [];

  if (typeof seriesData[0] === "number") {
    const yValues = seriesData as number[];
    const xs = xValues ?? yValues.map((_, i) => i);
    return yValues.map((y, i) => ({ x: xs[i] ?? i, y }));
  }

  return (seriesData as Array<[number, number]>).map(([x, y]) => ({ x, y }));
}

function formatThresholdValue(value: number): string {
  if (Math.abs(value) >= 100) return value.toFixed(2);
  if (Math.abs(value) >= 1) return value.toFixed(3);
  return value.toFixed(4);
}

type MarkLineDatum = {
  yAxis: number;
  name: string;
  lineStyle: { color: string; type: "solid" | "dashed" | "dotted"; width: number };
  label: {
    show: boolean;
    formatter: string;
    color: string;
    fontSize: number;
    fontWeight: number;
    position: "insideEndTop";
  };
};

export function buildThresholdMarkLineData(thresholds: GraphThresholdSet): MarkLineDatum[] {
  const data: MarkLineDatum[] = [];

  for (const level of THRESHOLD_LEVEL_ORDER) {
    const value = thresholds[level];
    if (value === undefined) continue;
    const meta = THRESHOLD_LEVEL_META[level];
    data.push({
      yAxis: value,
      name: meta.label,
      lineStyle: { color: meta.color, type: meta.lineType, width: 1.5 },
      label: {
        show: true,
        formatter: `${meta.label}: ${formatThresholdValue(value)}`,
        color: meta.color,
        fontSize: 11,
        fontWeight: 600,
        position: "insideEndTop",
      },
    });
  }

  return data;
}

export function buildThresholdMarkLineConfig(
  thresholds: GraphThresholdSet,
  options: ThresholdOverlayOptions = {}
) {
  if (options.showThresholds === false) return undefined;
  const data = buildThresholdMarkLineData(thresholds);
  if (data.length === 0) return undefined;
  return {
    symbol: ["none", "none"],
    silent: true,
    z: 4,
    data,
  };
}

export function computeShadeUpperBound(
  points: SeriesPoint[],
  thresholds: GraphThresholdSet,
  yAxisMax?: number
): number {
  const dataMax = points.reduce((max, p) => (p.y > max ? p.y : max), -Infinity);
  const thresholdMax = Math.max(
    thresholds.critical ?? -Infinity,
    thresholds.warning ?? -Infinity,
    thresholds.normal ?? -Infinity
  );
  const candidate = Math.max(
    Number.isFinite(dataMax) ? dataMax : 0,
    Number.isFinite(thresholdMax) ? thresholdMax : 0
  );
  const padded = candidate * 1.12 + 0.001;
  if (yAxisMax !== undefined && Number.isFinite(yAxisMax)) {
    return Math.max(yAxisMax, padded);
  }
  return padded;
}

export function buildThresholdMarkAreaConfig(
  thresholds: GraphThresholdSet,
  points: SeriesPoint[],
  options: ThresholdOverlayOptions = {},
  yAxisMax?: number
) {
  if (options.showThresholds === false || options.showShading === false) return undefined;

  const upper = computeShadeUpperBound(points, thresholds, yAxisMax);
  const areas: Array<[{ yAxis: number; itemStyle: { color: string } }, { yAxis: number }]> = [];

  if (thresholds.warning !== undefined) {
    areas.push([
      { yAxis: thresholds.warning, itemStyle: { color: THRESHOLD_LEVEL_META.warning.shadeColor } },
      { yAxis: upper },
    ]);
  }

  if (thresholds.critical !== undefined) {
    areas.push([
      { yAxis: thresholds.critical, itemStyle: { color: THRESHOLD_LEVEL_META.critical.shadeColor } },
      { yAxis: upper },
    ]);
  }

  if (areas.length === 0) return undefined;

  return {
    silent: true,
    z: 1,
    data: areas,
  };
}

const MAX_CROSSINGS_PER_LEVEL = 24;

function findThresholdCrossings(
  points: SeriesPoint[],
  threshold: number,
  level: ThresholdLevel
): Array<{ name: string; coord: [number, number]; itemStyle: { color: string; borderColor: string } }> {
  const crossings: Array<{
    name: string;
    coord: [number, number];
    itemStyle: { color: string; borderColor: string };
  }> = [];
  if (points.length < 2) return crossings;

  const meta = THRESHOLD_LEVEL_META[level];
  const step = Math.max(1, Math.floor(points.length / MAX_CROSSINGS_PER_LEVEL));

  for (let i = 1; i < points.length; i += step) {
    const prev = points[i - 1];
    const curr = points[i];
    const prevAbove = prev.y >= threshold;
    const currAbove = curr.y >= threshold;
    if (prevAbove === currAbove) continue;

    const dy = curr.y - prev.y;
    if (dy === 0) continue;
    const ratio = (threshold - prev.y) / dy;
    const x = prev.x + ratio * (curr.x - prev.x);
    crossings.push({
      name: `${meta.label} Crossing`,
      coord: [x, threshold],
      itemStyle: { color: meta.crossingColor, borderColor: "#FFFFFF" },
    });
    if (crossings.length >= MAX_CROSSINGS_PER_LEVEL) break;
  }

  return crossings;
}

export function buildThresholdCrossingMarkPointConfig(
  points: SeriesPoint[],
  thresholds: GraphThresholdSet,
  options: ThresholdOverlayOptions = {}
) {
  if (options.showThresholds === false || options.showCrossings === false) return undefined;

  const data: Array<{
    name: string;
    coord: [number, number];
    itemStyle: { color: string; borderColor: string };
  }> = [];

  for (const level of THRESHOLD_LEVEL_ORDER) {
    const value = thresholds[level];
    if (value === undefined) continue;
    data.push(...findThresholdCrossings(points, value, level));
  }

  if (data.length === 0) return undefined;

  return {
    symbol: "circle",
    symbolSize: 8,
    z: 6,
    label: { show: false },
    data,
  };
}

export interface ThresholdSeriesOverlay {
  markLine?: ReturnType<typeof buildThresholdMarkLineConfig>;
  markArea?: ReturnType<typeof buildThresholdMarkAreaConfig>;
  markPoint?: ReturnType<typeof buildThresholdCrossingMarkPointConfig>;
}

export function buildThresholdSeriesOverlay(
  points: SeriesPoint[],
  plot: PlotSeries | undefined,
  options: ThresholdOverlayOptions = {},
  yAxisMax?: number
): ThresholdSeriesOverlay {
  const thresholds = options.thresholds ?? resolveGraphThresholds(plot);
  if (!hasConfiguredThresholds(thresholds)) {
    return {};
  }

  return {
    markLine: buildThresholdMarkLineConfig(thresholds, options),
    markArea: buildThresholdMarkAreaConfig(thresholds, points, options, yAxisMax),
    markPoint: buildThresholdCrossingMarkPointConfig(points, thresholds, options),
  };
}

export function mergeMarkPointConfigs(
  primary: Record<string, unknown> | undefined,
  threshold: Record<string, unknown> | undefined
) {
  if (!primary && !threshold) return undefined;
  if (!primary) return threshold;
  if (!threshold) return primary;

  const primaryData = Array.isArray(primary.data) ? primary.data : [];
  const thresholdData = Array.isArray(threshold.data) ? threshold.data : [];

  return {
    ...primary,
    data: [...primaryData, ...thresholdData],
  };
}

export function mergeMarkLineConfigs(
  threshold: Record<string, unknown> | undefined,
  extra: Array<Record<string, unknown>> = []
) {
  const thresholdData = Array.isArray(threshold?.data) ? threshold.data : [];
  const combined = [...thresholdData, ...extra];
  if (combined.length === 0) return undefined;
  return {
    symbol: ["none", "none"],
    silent: true,
    z: 4,
    data: combined,
  };
}
