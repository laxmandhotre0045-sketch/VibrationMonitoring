import type { EChartsOption } from "echarts";
import type { PlotSeries } from "@/types/measurements";
import { computeOrbitAxisBounds, expandBoundsForThresholds } from "./chart-bounds";
import { downsampleWaveformSeries } from "./chart-data";
import { echartsThresholdValues } from "./chart-thresholds";
import {
  buildThresholdSeriesOverlay,
  extractSeriesPoints,
  type ThresholdOverlayOptions,
} from "./threshold-overlay";
import {
  baseAxisStyle,
  baseTooltip,
  CHART_GRID,
  CHART_TOOLBOX_OFF,
  CHART_X_AXIS_DATA_ZOOM,
  ECHARTS_BRAND,
  fixedYAxisConfig,
} from "./echarts-theme";

const ORBIT_MAX_POINTS = 8192;

export function buildOrbitOption(
  plot: PlotSeries,
  overlayOptions: ThresholdOverlayOptions = {}
): EChartsOption {
  const { x, y } = downsampleWaveformSeries(plot.x, plot.y, ORBIT_MAX_POINTS);
  const seriesData = x.map((xi, i) => [xi, y[i]] as [number, number]);
  const points = extractSeriesPoints(seriesData);
  const yRange = expandBoundsForThresholds(
    computeOrbitAxisBounds(plot.x, plot.y),
    echartsThresholdValues(plot, overlayOptions)
  );
  const thresholdOverlay = buildThresholdSeriesOverlay(
    points,
    plot,
    { showShading: true, showCrossings: true, ...overlayOptions },
    yRange?.[1]
  );

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
        const [xi, yi] = point.value as [number, number];
        return [
          `<span style="font-weight:600;color:${ECHARTS_BRAND.blue}">${plot.title}</span>`,
          `${plot.x_label}: <b>${xi.toFixed(4)}</b>`,
          `${plot.y_label}: <b>${yi.toFixed(4)}</b>`,
        ].join("<br/>");
      },
    },
    toolbox: CHART_TOOLBOX_OFF,
    dataZoom: CHART_X_AXIS_DATA_ZOOM,
    xAxis: {
      type: "value",
      name: plot.x_label,
      nameLocation: "middle",
      nameGap: 30,
      nameTextStyle: {
        color: ECHARTS_BRAND.blue,
        fontFamily: ECHARTS_BRAND.font,
        fontSize: 13,
        fontWeight: 500,
      },
      ...baseAxisStyle(),
    },
    yAxis: {
      type: "value",
      name: plot.y_label,
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
        name: plot.title,
        showSymbol: false,
        smooth: false,
        lineStyle: { color: ECHARTS_BRAND.blue, width: 1.5 },
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
