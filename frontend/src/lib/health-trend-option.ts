import type { EChartsOption } from "echarts";
import type { HealthMetricTrend } from "@/types/health-status";
import { echartsThresholdMarkLineConfig } from "./chart-thresholds";
import {
  baseAxisStyle,
  baseTooltip,
  ECHARTS_BRAND,
} from "./echarts-theme";

const HEALTH_CHART_GRID = {
  left: 44,
  right: 12,
  top: 16,
  bottom: 28,
  containLabel: false,
} as const;

function formatMetricValue(value: number, unit: string): string {
  if (!Number.isFinite(value)) return "—";
  if (unit === "%" || unit === "°C") return `${value.toFixed(1)}${unit}`;
  if (Math.abs(value) >= 100) return value.toFixed(2);
  if (Math.abs(value) >= 1) return value.toFixed(3);
  return value.toFixed(4);
}

export function buildHealthTrendOption(metric: HealthMetricTrend): EChartsOption {
  const seriesData = metric.trendX.map((x, i) => [x, metric.trendY[i]] as [number, number]);
  const thresholds = {
    warning: metric.warningThreshold,
    danger: metric.dangerThreshold,
  };
  const thresholdMarkLine = echartsThresholdMarkLineConfig(thresholds);
  const yValues = metric.trendY.filter((v) => Number.isFinite(v));
  const yMin = yValues.length ? Math.min(...yValues) : 0;
  const yMax = yValues.length ? Math.max(...yValues) : 1;
  const padding = (yMax - yMin) * 0.12 || 0.1;

  return {
    backgroundColor: ECHARTS_BRAND.plot,
    animation: false,
    grid: HEALTH_CHART_GRID,
    tooltip: {
      ...baseTooltip,
      formatter(params) {
        const items = Array.isArray(params) ? params : [params];
        const point = items[0];
        if (!point || !Array.isArray(point.value)) return "";
        const [, y] = point.value as [number, number];
        const unitSuffix = metric.unit ? ` ${metric.unit}` : "";
        return [
          `<span style="font-weight:600;color:${ECHARTS_BRAND.blue}">${metric.label}</span>`,
          `Value: <b>${formatMetricValue(y, metric.unit)}${unitSuffix}</b>`,
        ].join("<br/>");
      },
    },
    xAxis: {
      type: "value",
      show: true,
      ...baseAxisStyle(),
      axisLabel: { show: false },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      show: true,
      min: yMin - padding,
      max: yMax + padding,
      scale: false,
      ...baseAxisStyle(),
      axisLabel: {
        ...baseAxisStyle().axisLabel,
        fontSize: 10,
        formatter: (v: number) => formatMetricValue(v, metric.unit),
      },
    },
    series: [
      {
        type: "line",
        data: seriesData,
        showSymbol: false,
        smooth: true,
        lineStyle: { color: ECHARTS_BRAND.blue, width: 2 },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(21, 54, 109, 0.18)" },
              { offset: 1, color: "rgba(21, 54, 109, 0.02)" },
            ],
          },
        },
        markLine: thresholdMarkLine,
      },
    ],
  };
}

export function formatHealthMetricDisplay(value: number | null, unit: string): string {
  if (value === null || !Number.isFinite(value)) return "—";
  const suffix = unit ? ` ${unit}` : "";
  return `${formatMetricValue(value, unit)}${suffix}`;
}
