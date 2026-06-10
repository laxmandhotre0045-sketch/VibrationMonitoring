import type { Data } from "plotly.js";
import type { PlotSeries } from "@/types/measurements";
import { computeYAxisBounds, expandBoundsForThresholds } from "./chart-bounds";
import { getPlotThresholds, thresholdValues } from "./chart-thresholds";
import { PLOTLY_BRAND, PLOTLY_TRACE } from "./plotly-theme";

const MAX_POINTS = 2000;

/** Downsample for smooth Plotly interaction — does not alter backend calculations. */
export function downsampleSeries(
  x: number[],
  y: number[],
  maxPoints = MAX_POINTS
): { x: number[]; y: number[] } {
  if (x.length <= maxPoints) return { x, y };
  const step = Math.ceil(x.length / maxPoints);
  return {
    x: x.filter((_, i) => i % step === 0),
    y: y.filter((_, i) => i % step === 0),
  };
}

function isOrbitPlot(plot: PlotSeries): boolean {
  const style = plot.metadata?.plot_style as string | undefined;
  return plot.plot_type === "circular_time_waveform" || style === "orbit";
}

function isSpectrumPlot(plot: PlotSeries): boolean {
  return plot.plot_type === "fft_spectrum" || plot.plot_type === "envelope_spectrum";
}

export function plotSeriesToTrace(plot: PlotSeries): Data {
  const { x, y } = downsampleSeries(plot.x, plot.y);
  const orbit = isOrbitPlot(plot);
  const spectrum = isSpectrumPlot(plot);
  const timeWaveform = plot.plot_type === "time_waveform";

  const hover = `${plot.x_label}: %{x:.4f}<br>${plot.y_label}: %{y:.4f}<extra></extra>`;

  if (spectrum) {
    return {
      type: "scatter",
      mode: "lines",
      x,
      y,
      name: plot.title,
      line: { color: PLOTLY_BRAND.amber, width: 1.5 },
      hovertemplate: hover,
    };
  }

  return {
    type: "scatter",
    mode: "lines",
    x,
    y,
    name: plot.title,
    line: PLOTLY_TRACE.line,
    fill: timeWaveform && !orbit ? PLOTLY_TRACE.fill : undefined,
    fillcolor: timeWaveform && !orbit ? PLOTLY_TRACE.fillcolor : undefined,
    hovertemplate: hover,
  };
}

export function plotSeriesLayoutOptions(plot: PlotSeries): {
  yRange: [number, number] | undefined;
} {
  const thresholds = getPlotThresholds(plot);
  const yRange = expandBoundsForThresholds(
    computeYAxisBounds(plot.y),
    thresholdValues(thresholds)
  );
  return { yRange };
}
