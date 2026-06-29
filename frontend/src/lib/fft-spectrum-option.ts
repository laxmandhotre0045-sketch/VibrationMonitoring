import type { EChartsOption } from "echarts";
import type { PlotSeries } from "@/types/measurements";
import { computeYAxisBounds, expandBoundsForThresholds } from "./chart-bounds";
import { downsampleSeries, resolveSpectrumPeak } from "./chart-data";
import { echartsThresholdValues } from "./chart-thresholds";
import {
  buildThresholdMarkLineConfig,
  buildThresholdSeriesOverlay,
  extractSeriesPoints,
  mergeMarkLineConfigs,
  mergeMarkPointConfigs,
  resolveGraphThresholds,
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
  formatFrequencyHz,
  formatMagnitude,
} from "./echarts-theme";

function buildDominantFrequencyMarkLine(
  peak: ReturnType<typeof resolveSpectrumPeak>
): Array<Record<string, unknown>> {
  if (peak === null) return [];
  return [
    {
      xAxis: peak.frequency,
      name: "Dominant",
      lineStyle: { color: ECHARTS_BRAND.orange, type: "solid", width: 1, opacity: 0.65 },
      label: {
        show: true,
        formatter: `Dominant ${formatFrequencyHz(peak.frequency)}`,
        color: ECHARTS_BRAND.blue,
        fontFamily: ECHARTS_BRAND.font,
        fontSize: 11,
        position: "insideEndTop",
      },
    },
  ];
}

export function buildFftSpectrumOption(
  plot: PlotSeries,
  overlayOptions: ThresholdOverlayOptions = {}
): EChartsOption {
  const { x, y } = downsampleSeries(plot.x, plot.y);
  const seriesData = x.map((freq, i) => [freq, y[i]] as [number, number]);
  const points = extractSeriesPoints(seriesData);
  const yRange = expandBoundsForThresholds(
    computeYAxisBounds(plot.y),
    echartsThresholdValues(plot, overlayOptions)
  );
  const peak = resolveSpectrumPeak(plot);
  const thresholds = overlayOptions.thresholds ?? resolveGraphThresholds(plot);
  const thresholdMarkLine = buildThresholdMarkLineConfig(thresholds, {
    showShading: false,
    showCrossings: false,
    ...overlayOptions,
  });
  const thresholdOverlay = buildThresholdSeriesOverlay(
    points,
    plot,
    { showShading: true, showCrossings: true, ...overlayOptions, thresholds },
    yRange?.[1]
  );

  const peakMarkPoint =
    peak !== null
      ? {
          symbol: "circle",
          symbolSize: 9,
          itemStyle: {
            color: ECHARTS_BRAND.orange,
            borderColor: ECHARTS_BRAND.paper,
            borderWidth: 2,
          },
          label: { show: false },
          data: [
            {
              name: "Peak",
              coord: [peak.frequency, peak.magnitude],
            },
          ],
        }
      : undefined;

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
        const [freq, mag] = point.value as [number, number];
        return [
          `<span style="font-weight:600;color:${ECHARTS_BRAND.blue}">${plot.title}</span>`,
          `Frequency: <b>${formatFrequencyHz(freq)}</b>`,
          `Magnitude: <b>${formatMagnitude(mag)}</b>`,
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
        lineStyle: { color: ECHARTS_BRAND.amber, width: 1.5 },
        emphasis: {
          focus: "series",
          lineStyle: { width: 2, color: ECHARTS_BRAND.orange },
        },
        data: seriesData,
        markPoint: mergeMarkPointConfigs(
          peakMarkPoint as Record<string, unknown> | undefined,
          thresholdOverlay.markPoint as Record<string, unknown> | undefined
        ),
        markLine: mergeMarkLineConfigs(
          thresholdMarkLine as Record<string, unknown> | undefined,
          buildDominantFrequencyMarkLine(peak)
        ),
        markArea: thresholdOverlay.markArea,
      },
    ],
  };
}
