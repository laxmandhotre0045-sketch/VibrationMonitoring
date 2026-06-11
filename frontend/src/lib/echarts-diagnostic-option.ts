import type { EChartsOption } from "echarts";
import type { PlotSeries } from "@/types/measurements";
import { buildEnvelopeSpectrumOption } from "./envelope-spectrum-option";
import { buildFftSpectrumOption } from "./fft-spectrum-option";
import { buildOrbitOption } from "./orbit-option";
import { buildTrendOption } from "./trend-option";
import { buildTimeWaveformOption } from "./waveform-option";

/** Build the ECharts option for any diagnostic plot type. */
export function buildDiagnosticChartOption(
  plot: PlotSeries,
  samplingRateHz?: number
): EChartsOption {
  switch (plot.plot_type) {
    case "time_waveform":
      return buildTimeWaveformOption(plot, samplingRateHz);
    case "fft_spectrum":
      return buildFftSpectrumOption(plot);
    case "envelope_spectrum":
      return buildEnvelopeSpectrumOption(plot);
    case "circular_time_waveform":
      return buildOrbitOption(plot);
    case "trend_plot":
      return buildTrendOption(plot);
    default:
      return buildTimeWaveformOption(plot, samplingRateHz);
  }
}
