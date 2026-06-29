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

/**
 * Min/max bucket downsampling — preserves peaks for oscillating waveforms (sine, vibration).
 * Outputs up to maxPoints (pairs min+max per bucket).
 */
export function downsampleWaveformSeries(
  x: number[],
  y: number[],
  maxPoints = 8192
): { x: number[]; y: number[] } {
  if (x.length <= maxPoints || y.length !== x.length) return { x, y };

  const bucketCount = Math.max(1, Math.floor(maxPoints / 2));
  const bucketSize = x.length / bucketCount;
  const outX: number[] = [];
  const outY: number[] = [];

  for (let b = 0; b < bucketCount; b++) {
    const start = Math.floor(b * bucketSize);
    const end = Math.min(x.length, Math.floor((b + 1) * bucketSize));
    if (end - start < 1) continue;

    let minIdx = start;
    let maxIdx = start;
    for (let i = start + 1; i < end; i++) {
      if (y[i] < y[minIdx]) minIdx = i;
      if (y[i] > y[maxIdx]) maxIdx = i;
    }

    if (minIdx <= maxIdx) {
      outX.push(x[minIdx], x[maxIdx]);
      outY.push(y[minIdx], y[maxIdx]);
    } else {
      outX.push(x[maxIdx], x[minIdx]);
      outY.push(y[maxIdx], y[minIdx]);
    }
  }

  return { x: outX, y: outY };
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
