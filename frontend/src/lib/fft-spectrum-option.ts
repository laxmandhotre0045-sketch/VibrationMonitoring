import type { EChartsOption } from "echarts";
import type { PlotSeries } from "@/types/measurements";
import { computeYAxisBounds, expandBoundsForThresholds } from "./chart-bounds";
import { downsampleSeries, resolveSpectrumPeak } from "./chart-data";
import { getPlotThresholds, thresholdValues } from "./chart-thresholds";
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

type MarkLineDatum = {
  yAxis?: number;
  xAxis?: number;
  name?: string;
  lineStyle?: { color: string; type?: "solid" | "dashed" | "dotted"; width?: number; opacity?: number };
  label?: {
    show?: boolean;
    formatter?: string;
    color?: string;
    fontFamily?: string;
    fontSize?: number;
    position?: "insideEndTop";
  };
};

function buildMarkLineData(
  thresholds: ReturnType<typeof getPlotThresholds>,
  peak: ReturnType<typeof resolveSpectrumPeak>
): MarkLineDatum[] {
  const data: MarkLineDatum[] = [];

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

  if (peak !== null) {
    data.push({
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
    });
  }

  return data;
}

export function buildFftSpectrumOption(plot: PlotSeries): EChartsOption {
  const { x, y } = downsampleSeries(plot.x, plot.y);
  const seriesData = x.map((freq, i) => [freq, y[i]] as [number, number]);
  const thresholds = getPlotThresholds(plot);
  const yRange = expandBoundsForThresholds(
    computeYAxisBounds(plot.y),
    thresholdValues(thresholds)
  );
  const peak = resolveSpectrumPeak(plot);
  const markLineData = buildMarkLineData(thresholds, peak);

  const markPoint =
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
        markPoint,
        markLine:
          markLineData.length > 0
            ? {
                symbol: ["none", "none"],
                silent: true,
                data: markLineData,
              }
            : undefined,
      },
    ],
  };
}
