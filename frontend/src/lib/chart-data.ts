import type { PlotSeries } from "@/types/measurements";

const SPECTRUM_MAX_POINTS = 2000;

/** Downsample for smooth rendering — does not alter backend calculations. */
export function downsampleSeries(
  x: number[],
  y: number[],
  maxPoints = SPECTRUM_MAX_POINTS
): { x: number[]; y: number[] } {
  if (x.length <= maxPoints) return { x, y };
  const step = Math.ceil(x.length / maxPoints);
  return {
    x: x.filter((_, i) => i % step === 0),
    y: y.filter((_, i) => i % step === 0),
  };
}

export interface SpectrumPeak {
  frequency: number;
  magnitude: number;
  index: number;
}

function readMetadataNumber(metadata: Record<string, unknown>, key: string): number | undefined {
  const value = metadata[key];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

/** Peak from API metadata when provided; otherwise from existing spectrum arrays. */
export function resolveSpectrumPeak(plot: PlotSeries): SpectrumPeak | null {
  const metaFreq =
    readMetadataNumber(plot.metadata, "dominant_frequency_hz") ??
    readMetadataNumber(plot.metadata, "peak_frequency_hz");
  const metaMag = readMetadataNumber(plot.metadata, "peak_magnitude");

  if (metaFreq !== undefined && metaMag !== undefined) {
    return { frequency: metaFreq, magnitude: metaMag, index: -1 };
  }

  return findSpectrumPeak(plot.x, plot.y);
}

/** Dominant frequency = max magnitude bin in the supplied spectrum data. */
export function findSpectrumPeak(x: number[], y: number[]): SpectrumPeak | null {
  if (x.length === 0 || y.length === 0) return null;

  let index = 0;
  let max = -Infinity;

  for (let i = 0; i < y.length; i++) {
    const value = y[i];
    if (!Number.isFinite(value)) continue;
    if (value > max) {
      max = value;
      index = i;
    }
  }

  if (!Number.isFinite(max)) return null;

  return {
    frequency: x[index],
    magnitude: max,
    index,
  };
}
