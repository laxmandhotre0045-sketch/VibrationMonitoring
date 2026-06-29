import type { DataZoomComponentOption, TooltipComponentOption } from "echarts";

/** SensoVibe ECharts brand tokens — aligned with Plotly diagnostic palette */
export const ECHARTS_BRAND = {
  blue: "#15366D",
  amber: "#D98C00",
  orange: "#FF6B00",
  grid: "#F0EBE3",
  axis: "#E8E4DE",
  paper: "#FFFFFF",
  plot: "#FFFDF8",
  muted: "#5C6B7A",
  font: "Inter, system-ui, sans-serif",
} as const;

export const CHART_GRID = {
  left: 58,
  right: 28,
  top: 32,
  bottom: 72,
  containLabel: false,
} as const;

/** Custom ChartToolbar handles export/zoom — hide default ECharts toolbox. */
export const CHART_TOOLBOX_OFF = {
  show: false,
} as const;

/** X-axis zoom/pan only — no Y-axis dataZoom */
export const CHART_X_AXIS_DATA_ZOOM: DataZoomComponentOption[] = [
  {
    type: "inside",
    xAxisIndex: 0,
    filterMode: "none",
    zoomOnMouseWheel: true,
    moveOnMouseMove: true,
    moveOnMouseWheel: false,
  },
  {
    type: "slider",
    xAxisIndex: 0,
    filterMode: "none",
    height: 26,
    bottom: 10,
    borderColor: ECHARTS_BRAND.axis,
    fillerColor: "rgba(217, 140, 0, 0.12)",
    handleStyle: { color: ECHARTS_BRAND.amber, borderColor: ECHARTS_BRAND.amber },
    dataBackground: {
      lineStyle: { color: ECHARTS_BRAND.axis },
      areaStyle: { color: "rgba(21, 54, 109, 0.04)" },
    },
    selectedDataBackground: {
      lineStyle: { color: ECHARTS_BRAND.amber },
      areaStyle: { color: "rgba(217, 140, 0, 0.18)" },
    },
    textStyle: { color: ECHARTS_BRAND.muted, fontFamily: ECHARTS_BRAND.font, fontSize: 11 },
  },
];

export function fixedYAxisConfig(min?: number, max?: number) {
  return {
    scale: false as const,
    ...(min !== undefined && max !== undefined ? { min, max } : {}),
  };
}

export function baseAxisStyle() {
  return {
    axisLine: { lineStyle: { color: ECHARTS_BRAND.axis, width: 1 } },
    axisTick: { lineStyle: { color: ECHARTS_BRAND.axis } },
    axisLabel: {
      color: ECHARTS_BRAND.muted,
      fontFamily: ECHARTS_BRAND.font,
      fontSize: 12,
    },
    splitLine: {
      lineStyle: { color: ECHARTS_BRAND.grid, width: 1 },
    },
  };
}

export const baseTooltip: TooltipComponentOption = {
  trigger: "axis",
  axisPointer: {
    type: "cross",
    crossStyle: { color: ECHARTS_BRAND.amber, width: 1, type: "dashed" },
    lineStyle: { color: ECHARTS_BRAND.amber, width: 1, type: "dashed" },
    label: {
      backgroundColor: ECHARTS_BRAND.blue,
      color: "#fff",
      fontFamily: ECHARTS_BRAND.font,
      fontSize: 11,
    },
  },
  backgroundColor: ECHARTS_BRAND.plot,
  borderColor: ECHARTS_BRAND.amber,
  borderWidth: 1,
  padding: [10, 14],
  textStyle: {
    color: ECHARTS_BRAND.blue,
    fontFamily: ECHARTS_BRAND.font,
    fontSize: 13,
  },
  confine: true,
};

export function formatFrequencyHz(value: number): string {
  if (!Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  if (abs >= 1000) return `${value.toFixed(1)} Hz`;
  if (abs >= 100) return `${value.toFixed(2)} Hz`;
  if (abs >= 1) return `${value.toFixed(3)} Hz`;
  return `${value.toFixed(4)} Hz`;
}

export { formatTimeMs } from "./waveform-time-axis";

export function formatMagnitude(value: number): string {
  if (!Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  if (abs >= 1000) return value.toExponential(3);
  if (abs >= 1) return value.toFixed(4);
  return value.toExponential(3);
}
