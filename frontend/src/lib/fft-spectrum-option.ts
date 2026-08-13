import type { EChartsOption } from "echarts";
import type { PlotSeries } from "@/types/measurements";
import {
  buildHarmonicReferenceLines,
  buildNyquistReferenceLine,
  mergeSpectrumReferenceLines,
} from "./chart-reference-lines";
import { computeYAxisBounds, expandBoundsForThresholds } from "./chart-bounds";
import { downsampleSeries, resolveSpectrumPeak } from "./chart-data";
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
  formatFrequencyHz,
  industrialAxisConfig,
} from "./echarts-theme";
import {
  buildVizContextFromPlot,
  frequencyResolutionHz,
  INDUSTRIAL_AXIS_GRID,
  INDUSTRIAL_TRACE_COLORS,
  nyquistFrequencyHz,
} from "./industrial-viz-standards";
import {
  buildThresholdMarkLineConfig,
  buildThresholdSeriesOverlay,
  extractSeriesPoints,
  mergeMarkLineConfigs,
  mergeMarkPointConfigs,
  resolveGraphThresholds,
  type ThresholdOverlayOptions,
} from "./threshold-overlay";

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
  configuredSampleRateHz?: number,
  overlayOptions: ThresholdOverlayOptions = {}
): EChartsOption {
  const { x, y } = downsampleSeries(plot.x, plot.y);
  const seriesData = x.map((freq, i) => [freq, y[i]] as [number, number]);
  const points = extractSeriesPoints(seriesData);
  const vizContext = buildVizContextFromPlot(
    plot.metadata,
    plot.y_label,
    configuredSampleRateHz,
    plot.y.length
  );
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

  const sampleRate = vizContext.sampleRateHz;
  const fftLines = vizContext.fftLines ?? plot.y.length;
  const nyquist = sampleRate ? nyquistFrequencyHz(sampleRate) : null;
  const freqResolution =
    sampleRate && fftLines ? frequencyResolutionHz(sampleRate, fftLines) : null;

  const referenceLines = mergeSpectrumReferenceLines(
    sampleRate ? buildNyquistReferenceLine(sampleRate) : null,
    vizContext.rpm ? buildHarmonicReferenceLines(vizContext.rpm) : [],
    buildDominantFrequencyMarkLine(peak)
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

  const traceColor =
    plot.plot_type === "envelope_spectrum"
      ? INDUSTRIAL_TRACE_COLORS.envelope_spectrum
      : INDUSTRIAL_TRACE_COLORS.fft_spectrum;

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
        const lines = [
          `<span style="font-weight:600;color:${ECHARTS_BRAND.blue}">${plot.title}</span>`,
          `Frequency: <b>${formatFrequencyHz(freq)}</b>`,
          `Magnitude: <b>${formatAmplitudeWithUnit(mag, vizContext.yUnit)}</b>`,
        ];
        if (freqResolution) {
          lines.push(
            `<span style="color:${ECHARTS_BRAND.muted};font-size:12px">Δf: ${formatFrequencyHz(freqResolution)}</span>`
          );
        }
        if (nyquist) {
          lines.push(
            `<span style="color:${ECHARTS_BRAND.muted};font-size:12px">Nyquist: ${formatFrequencyHz(nyquist)}</span>`
          );
        }
        if (vizContext.rpm) {
          lines.push(
            `<span style="color:${ECHARTS_BRAND.muted};font-size:12px">Shaft speed: ${vizContext.rpm.toFixed(1)} RPM</span>`
          );
        }
        return lines.join("<br/>");
      },
    },
    toolbox: CHART_TOOLBOX_OFF,
    dataZoom: CHART_X_AXIS_DATA_ZOOM,
    xAxis: {
      type: "value",
      name: plot.x_label,
      nameLocation: "middle",
      nameGap: 30,
      min: 0,
      ...(nyquist ? { max: nyquist } : {}),
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
        formatter: (value: number) => formatFrequencyHz(value),
      },
    },
    yAxis: {
      type: "value",
      name: plot.y_label,
      nameLocation: "middle",
      nameGap: 42,
      min: 0,
      nameTextStyle: {
        color: ECHARTS_BRAND.blue,
        fontFamily: ECHARTS_BRAND.font,
        fontSize: 13,
        fontWeight: 500,
      },
      ...baseAxisStyle(),
      ...industrialAxisConfig(INDUSTRIAL_AXIS_GRID.splitNumber),
      ...fixedYAxisConfig(Math.max(0, yRange?.[0] ?? 0), yRange?.[1]),
    },
    series: [
      {
        type: "line",
        name: plot.title,
        showSymbol: false,
        smooth: false,
        lineStyle: { color: traceColor, width: 1.5 },
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
          referenceLines
        ),
        markArea: thresholdOverlay.markArea,
      },
    ],
  };
}
