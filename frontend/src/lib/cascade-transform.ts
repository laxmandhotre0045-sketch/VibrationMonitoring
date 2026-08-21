/**
 * Cascade transform: the same WaterfallModel the 3D view renders, restacked into 2D.
 *
 * Both views consume one API response and one `buildWaterfallModel` result, so peak
 * frequencies, amplitudes, timestamps and capture numbers are identical by construction.
 *
 * The vertical axis here is a LAYOUT device, not a physical quantity:
 *
 *     displayY = baseline(captureIndex) + amplitude / amplitudeMax * traceHeight
 *
 * The true amplitude of every plotted point is kept alongside it in `amplitudes[]`, so
 * tooltips and exports always report physical values, never the stacked position.
 */
import type { WaterfallModel } from "./waterfall-adapter";

export interface CascadePeakPoint {
  captureIndex: number;
  captureNumber: number;
  frequency: number;
  /** Real FFT magnitude, exactly as the backend detected it. */
  amplitude: number;
  /** Stacked position used for drawing only. */
  displayY: number;
}

export interface CascadeTrace {
  captureIndex: number;
  captureNumber: number;
  uploadId: string;
  capturedAt: string;
  originalFilename: string | null;
  /** Zero-amplitude line for this capture. */
  baseline: number;
  color: string;
  /** [frequency, displayY] pairs handed to ECharts. */
  points: [number, number][];
  /** amplitudes[i] is the true magnitude of points[i]. Never dropped. */
  amplitudes: number[];
  /** Rounded peak frequencies for O(1) "is this point a peak?" lookups. */
  peakFrequencies: Set<number>;
  peaks: CascadePeakPoint[];
}

export interface CascadeModel {
  traces: CascadeTrace[];
  peaks: CascadePeakPoint[];
  /** Vertical distance between two consecutive capture baselines. */
  laneSpacing: number;
  /** Display height a full-scale peak occupies within its lane. */
  traceHeight: number;
  /** Global amplitude reference — one scale for every trace, so captures stay comparable. */
  amplitudeMax: number;
  frequencyRange: [number, number];
  displayRange: [number, number];
  totalPoints: number;
  droppedPoints: number;
  /** Approximate pixels per capture lane at the current chart height. */
  lanePx: number;
  /** False when lanes are too thin to read — the UI surfaces a hint. */
  isReadable: boolean;
}

/** Below this many pixels per lane the traces start merging visually. */
const MIN_READABLE_LANE_PX = 9;

/** Hard ceiling on points per trace before peak-preserving decimation kicks in. */
export const CASCADE_MAX_POINTS_PER_TRACE = 1024;

/**
 * How much of a lane a full-scale peak may fill. Tall lanes (few captures) can show more
 * shape; thin lanes need less overlap to stay separable.
 */
export function laneFillRatio(lanePx: number): number {
  if (lanePx >= 40) return 0.95;
  if (lanePx <= 10) return 0.7;
  return 0.7 + ((lanePx - 10) / 30) * 0.25;
}

function roundFrequency(frequency: number): number {
  return Math.round(frequency * 1000) / 1000;
}

/**
 * Bucketed max decimation that force-keeps every detected peak.
 *
 * Plain max-per-bucket already retains local maxima, but a peak sitting next to a taller
 * neighbour inside the same bucket would be lost — so peak bins are merged back in.
 */
function decimatePreservingPeaks(
  frequencies: number[],
  amplitudes: number[],
  peakFrequencies: Set<number>,
  maxPoints: number
): { frequencies: number[]; amplitudes: number[] } {
  const n = frequencies.length;
  if (n <= maxPoints) return { frequencies, amplitudes };

  const keep = new Set<number>();
  const bucketSize = n / maxPoints;

  for (let b = 0; b < maxPoints; b += 1) {
    const start = Math.floor(b * bucketSize);
    const end = Math.min(n, Math.floor((b + 1) * bucketSize));
    if (end <= start) continue;
    let best = start;
    for (let i = start + 1; i < end; i += 1) {
      if (amplitudes[i] > amplitudes[best]) best = i;
    }
    keep.add(best);
  }

  // Endpoints anchor the trace to the real frequency range.
  keep.add(0);
  keep.add(n - 1);

  if (peakFrequencies.size > 0) {
    for (let i = 0; i < n; i += 1) {
      if (peakFrequencies.has(roundFrequency(frequencies[i]))) keep.add(i);
    }
  }

  const indices = Array.from(keep).sort((a, b) => a - b);
  return {
    frequencies: indices.map((i) => frequencies[i]),
    amplitudes: indices.map((i) => amplitudes[i]),
  };
}

export interface BuildCascadeModelOptions {
  /** Chart plot height in px — drives lane spacing and fill ratio. */
  heightPx: number;
  maxPointsPerTrace?: number;
}

export function buildCascadeModel(
  model: WaterfallModel,
  { heightPx, maxPointsPerTrace = CASCADE_MAX_POINTS_PER_TRACE }: BuildCascadeModelOptions
): CascadeModel {
  const lineCount = model.lines.length;
  const amplitudeMax = model.ranges.amplitude[1] || 1;

  // Baselines span 0..1 regardless of N, so the axis reads the same at any capture count.
  const laneSpacing = lineCount > 1 ? 1 / (lineCount - 1) : 1;
  const lanePx = lineCount > 0 ? heightPx / lineCount : heightPx;
  const traceHeight = laneSpacing * laneFillRatio(lanePx);

  const peaksByCapture = new Map<number, CascadePeakPoint[]>();
  const peakFreqsByCapture = new Map<number, Set<number>>();

  for (const peak of model.peaks) {
    const [frequency, captureNumber, amplitude] = peak.point;
    const baseline = (captureNumber - 1) * laneSpacing;
    const entry: CascadePeakPoint = {
      captureIndex: peak.captureIndex,
      captureNumber,
      frequency,
      amplitude,
      displayY: baseline + (amplitude / amplitudeMax) * traceHeight,
    };
    const bucket = peaksByCapture.get(captureNumber);
    if (bucket) bucket.push(entry);
    else peaksByCapture.set(captureNumber, [entry]);

    const freqSet = peakFreqsByCapture.get(captureNumber);
    if (freqSet) freqSet.add(roundFrequency(frequency));
    else peakFreqsByCapture.set(captureNumber, new Set([roundFrequency(frequency)]));
  }

  const traces: CascadeTrace[] = [];
  const peaks: CascadePeakPoint[] = [];
  let totalPoints = 0;
  let droppedPoints = 0;
  let displayMax = 0;

  model.lines.forEach((line, index) => {
    const baseline = index * laneSpacing;
    const peakFrequencies = peakFreqsByCapture.get(line.captureNumber) ?? new Set<number>();

    const rawFrequencies: number[] = [];
    const rawAmplitudes: number[] = [];
    for (const [frequency, , amplitude] of line.points) {
      rawFrequencies.push(frequency);
      rawAmplitudes.push(amplitude);
    }

    const thinned = decimatePreservingPeaks(
      rawFrequencies,
      rawAmplitudes,
      peakFrequencies,
      maxPointsPerTrace
    );
    droppedPoints += rawFrequencies.length - thinned.frequencies.length;

    const points: [number, number][] = new Array(thinned.frequencies.length);
    for (let i = 0; i < thinned.frequencies.length; i += 1) {
      const displayY = baseline + (thinned.amplitudes[i] / amplitudeMax) * traceHeight;
      points[i] = [thinned.frequencies[i], displayY];
      if (displayY > displayMax) displayMax = displayY;
    }

    const tracePeaks = peaksByCapture.get(line.captureNumber) ?? [];
    peaks.push(...tracePeaks);
    totalPoints += points.length;

    traces.push({
      captureIndex: index,
      captureNumber: line.captureNumber,
      uploadId: line.uploadId,
      capturedAt: line.capturedAt,
      originalFilename: line.originalFilename,
      baseline,
      color: line.color,
      points,
      amplitudes: thinned.amplitudes,
      peakFrequencies,
      peaks: tracePeaks,
    });
  });

  const topBaseline = lineCount > 1 ? 1 : 0;
  const pad = traceHeight * 0.15;

  return {
    traces,
    peaks,
    laneSpacing,
    traceHeight,
    amplitudeMax,
    frequencyRange: model.ranges.frequency,
    displayRange: [-pad, Math.max(displayMax, topBaseline + traceHeight) + pad],
    totalPoints,
    droppedPoints,
    lanePx,
    isReadable: lanePx >= MIN_READABLE_LANE_PX,
  };
}

/** Capture number for a stacked Y position — used by the axis label formatter. */
export function captureNumberAtDisplayY(model: CascadeModel, displayY: number): number {
  return Math.round(displayY / model.laneSpacing) + 1;
}
