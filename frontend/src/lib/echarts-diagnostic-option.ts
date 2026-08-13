import type { EChartsOption } from "echarts";
import type { PlotSeries } from "@/types/measurements";
import type { ThresholdOverlayOptions } from "./threshold-overlay";
import { buildEnvelopeSpectrumOption } from "./envelope-spectrum-option";
import { buildFftSpectrumOption } from "./fft-spectrum-option";
import { buildOrbitOption } from "./orbit-option";
import { buildTrendOption } from "./trend-option";
import { buildTimeWaveformOption } from "./waveform-option";

/** Build the ECharts option for any diagnostic plot type. */
export function buildDiagnosticChartOption(
  plot: PlotSeries,
  samplingRateHz?: number,
  overlayOptions: ThresholdOverlayOptions = {}
): EChartsOption {
  switch (plot.plot_type) {
    case "time_waveform":
      return buildTimeWaveformOption(plot, samplingRateHz, overlayOptions);
    case "fft_spectrum":
      return buildFftSpectrumOption(plot, samplingRateHz, overlayOptions);
    case "envelope_spectrum":
      return buildEnvelopeSpectrumOption(plot, samplingRateHz, overlayOptions);
    case "circular_time_waveform":
      return buildOrbitOption(plot, overlayOptions);
    case "trend_plot":
      return buildTrendOption(plot, overlayOptions);
    default:
      return buildTimeWaveformOption(plot, samplingRateHz, overlayOptions);
  }
}
