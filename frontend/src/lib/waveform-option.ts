import type { EChartsOption } from "echarts";
import type { PlotSeries } from "@/types/measurements";
import {
  computeSymmetricYAxisBounds,
  expandBoundsForThresholds,
} from "./chart-bounds";
import { downsampleWaveformSeries } from "./chart-data";
import { echartsThresholdValues } from "./chart-thresholds";
import {
  baseAxisStyle,
  baseTooltip,
  CHART_GRID,
  CHART_TOOLBOX_OFF,
  CHART_X_AXIS_DATA_ZOOM,
  ECHARTS_BRAND,
  fixedYAxisConfig,
  formatAmplitudeWithUnit,
  industrialAxisConfig,
} from "./echarts-theme";
import {
  buildVizContextFromPlot,
  INDUSTRIAL_AXIS_GRID,
  INDUSTRIAL_TRACE_COLORS,
} from "./industrial-viz-standards";
import {
  buildThresholdSeriesOverlay,
  extractSeriesPoints,
  type ThresholdOverlayOptions,
} from "./threshold-overlay";
import {
  formatTimeMs,
  resolveSampleRateHz,
  withGeneratedTimeAxis,
} from "./waveform-time-axis";

const WAVEFORM_MAX_POINTS = 8192;

/** ECharts option builder for time waveform with frontend-generated ms time axis. */
export function buildTimeWaveformOption(
  plot: PlotSeries,
  configuredSampleRateHz?: number,
  overlayOptions: ThresholdOverlayOptions = {}
): EChartsOption {
  const displayPlot = withGeneratedTimeAxis(plot, configuredSampleRateHz);
  const { x, y } = downsampleWaveformSeries(displayPlot.x, displayPlot.y, WAVEFORM_MAX_POINTS);
  const seriesData = x.map((timeMs, i) => [timeMs, y[i]] as [number, number]);
  const points = extractSeriesPoints(seriesData);
  const vizContext = buildVizContextFromPlot(
    displayPlot.metadata,
    displayPlot.y_label,
    resolveSampleRateHz(displayPlot, configuredSampleRateHz),
    displayPlot.y.length
  );
  const yRange = expandBoundsForThresholds(
    computeSymmetricYAxisBounds(displayPlot.y),
    echartsThresholdValues(displayPlot, overlayOptions)
  );
  const sampleRateHz = vizContext.sampleRateHz ?? resolveSampleRateHz(plot, configuredSampleRateHz);
  const thresholdOverlay = buildThresholdSeriesOverlay(
    points,
    displayPlot,
    { showShading: true, showCrossings: true, ...overlayOptions },
    yRange?.[1]
  );
  const traceColor = INDUSTRIAL_TRACE_COLORS.time_waveform;

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
        const lines = [
          `<span style="font-weight:600;color:${ECHARTS_BRAND.blue}">${displayPlot.title}</span>`,
          `Time: <b>${formatTimeMs(timeMs)}</b>`,
          `Amplitude: <b>${formatAmplitudeWithUnit(amplitude, vizContext.yUnit)}</b>`,
          `<span style="color:${ECHARTS_BRAND.muted};font-size:12px">${sampleRateHz.toLocaleString()} Hz · ${displayPlot.y.length.toLocaleString()} samples</span>`,
        ];
        if (vizContext.sampleCount) {
          const durationMs = ((vizContext.sampleCount - 1) / sampleRateHz) * 1000;
          lines.push(
            `<span style="color:${ECHARTS_BRAND.muted};font-size:12px">Record length: ${formatTimeMs(durationMs)}</span>`
          );
        }
        return lines.join("<br/>");
      },
    },
    toolbox: CHART_TOOLBOX_OFF,
    dataZoom: CHART_X_AXIS_DATA_ZOOM,
    xAxis: {
      type: "value",
      name: displayPlot.x_label,
      nameLocation: "middle",
      nameGap: 30,
      min: 0,
      nameTextStyle: {
        color: ECHARTS_BRAND.blue,
        fontFamily: ECHARTS_BRAND.font,
        fontSize: 13,
        fontWeight: 500,
      },
      ...baseAxisStyle(),
      ...industrialAxisConfig(INDUSTRIAL_AXIS_GRID.splitNumber),
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
      ...industrialAxisConfig(INDUSTRIAL_AXIS_GRID.splitNumber),
      ...fixedYAxisConfig(yRange?.[0], yRange?.[1]),
    },
    series: [
      {
        type: "line",
        name: displayPlot.title,
        showSymbol: false,
        smooth: false,
        lineStyle: { color: traceColor, width: 1.5 },
        emphasis: {
          focus: "series",
          lineStyle: { width: 2, color: ECHARTS_BRAND.orange },
        },
        data: seriesData,
        markLine: thresholdOverlay.markLine,
        markArea: thresholdOverlay.markArea,
        markPoint: thresholdOverlay.markPoint,
      },
    ],
  };
}
