import type { PlotSeries } from "@/types/measurements";
import { buildFftSpectrumOption } from "./fft-spectrum-option";

/** Envelope spectrum shares the same frequency/magnitude structure as FFT. */
export function buildEnvelopeSpectrumOption(plot: PlotSeries) {
  return buildFftSpectrumOption(plot);
}
