import type { EChartsOption } from "echarts";
import type { PlotSeries } from "@/types/measurements";
import { computeYAxisBounds, expandBoundsForThresholds } from "./chart-bounds";
import { downsampleSeries } from "./chart-data";
import { getPlotThresholds, thresholdValues } from "./chart-thresholds";
import {
  baseAxisStyle,
  baseTooltip,
  CHART_GRID,
  CHART_TOOLBOX_OFF,
  CHART_X_AXIS_DATA_ZOOM,
  ECHARTS_BRAND,
  fixedYAxisConfig,
} from "./echarts-theme";
import {
  formatTimeMs,
  resolveSampleRateHz,
  withGeneratedTimeAxis,
} from "./waveform-time-axis";

const WAVEFORM_MAX_POINTS = 8192;

/**
 * ECharts option builder for time waveform — shares time-axis logic with Plotly path.
 * Ready for Phase 2 migration; not wired to DiagnosticChart yet.
 */
export function buildTimeWaveformOption(
  plot: PlotSeries,
  configuredSampleRateHz?: number
): EChartsOption {
  const displayPlot = withGeneratedTimeAxis(plot, configuredSampleRateHz);
  const { x, y } = downsampleSeries(displayPlot.x, displayPlot.y, WAVEFORM_MAX_POINTS);
  const seriesData = x.map((timeMs, i) => [timeMs, y[i]] as [number, number]);
  const thresholds = getPlotThresholds(displayPlot);
  const yRange = expandBoundsForThresholds(
    computeYAxisBounds(displayPlot.y),
    thresholdValues(thresholds)
  );
  const sampleRateHz = resolveSampleRateHz(plot, configuredSampleRateHz);

  return {
    backgroundColor: ECHARTS_BRAND.plot,
    animation: false,
    grid: CHART_GRID,
    tooltip: {
      ...baseTooltip,
      formatter(params) {
        const items = Array.isArray(params) ? params : [params];
        const point = items[0];
        if (!point || !Array.isArray(point.value)) return "";
        const [timeMs, amplitude] = point.value as [number, number];
        return [
          `<span style="font-weight:600;color:${ECHARTS_BRAND.blue}">${displayPlot.title}</span>`,
          `Time: <b>${formatTimeMs(timeMs)}</b>`,
          `Amplitude: <b>${amplitude.toFixed(4)}</b>`,
          `<span style="color:${ECHARTS_BRAND.muted};font-size:12px">${sampleRateHz.toLocaleString()} Hz · ${displayPlot.y.length} samples</span>`,
        ].join("<br/>");
      },
    },
    toolbox: CHART_TOOLBOX_OFF,
    dataZoom: CHART_X_AXIS_DATA_ZOOM,
    xAxis: {
      type: "value",
      name: displayPlot.x_label,
      nameLocation: "middle",
      nameGap: 30,
      nameTextStyle: {
        color: ECHARTS_BRAND.blue,
        fontFamily: ECHARTS_BRAND.font,
        fontSize: 13,
        fontWeight: 500,
      },
      ...baseAxisStyle(),
      axisLabel: {
        color: ECHARTS_BRAND.muted,
        fontFamily: ECHARTS_BRAND.font,
        fontSize: 12,
        formatter: (value: number) => formatTimeMs(value),
      },
    },
    yAxis: {
      type: "value",
      name: displayPlot.y_label,
      nameLocation: "middle",
      nameGap: 42,
      nameTextStyle: {
        color: ECHARTS_BRAND.blue,
        fontFamily: ECHARTS_BRAND.font,
        fontSize: 13,
        fontWeight: 500,
      },
      ...baseAxisStyle(),
      ...fixedYAxisConfig(yRange?.[0], yRange?.[1]),
    },
    series: [
      {
        type: "line",
        name: displayPlot.title,
        showSymbol: false,
        smooth: false,
        lineStyle: { color: ECHARTS_BRAND.blue, width: 1.5 },
        areaStyle: { color: "rgba(217, 140, 0, 0.12)" },
        emphasis: {
          focus: "series",
          lineStyle: { width: 2, color: ECHARTS_BRAND.orange },
        },
        data: seriesData,
      },
    ],
  };
}
