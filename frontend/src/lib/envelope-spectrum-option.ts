import type { PlotSeries } from "@/types/measurements";
import type { ThresholdOverlayOptions } from "./threshold-overlay";
import { buildFftSpectrumOption } from "./fft-spectrum-option";

/** Envelope spectrum shares the same frequency/magnitude structure as FFT. */
export function buildEnvelopeSpectrumOption(
  plot: PlotSeries,
  configuredSampleRateHz?: number,
  overlayOptions: ThresholdOverlayOptions = {}
) {
  return buildFftSpectrumOption(plot, configuredSampleRateHz, overlayOptions);
}
