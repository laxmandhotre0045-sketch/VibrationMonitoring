/**
 * Adapter: waterfall API response -> 3D-ready series.
 *
 * Axis mapping. The engineering view is frequency across, amplitude up, capture into
 * the screen. ECharts GL wants each datum as [xAxis3D, yAxis3D, zAxis3D] where
 * zAxis3D is the vertical one, so a point is stored as:
 *
 *     [frequency, captureNumber, amplitude]
 *      x: freq     y: depth      z: height
 *
 * which renders exactly as: X = Frequency (Hz), vertical = |A| peak, depth = Capture #.
 */
import type {
  WaterfallCapture,
  WaterfallPeak,
  WaterfallResponse,
} from "@/types/waterfall";

/** [x, y, z] = [frequency, captureNumber, amplitude]. */
export type WaterfallPoint3D = [number, number, number];

export interface WaterfallPeakPoint {
  point: WaterfallPoint3D;
  captureIndex: number;
}

export interface WaterfallLine {
  captureIndex: number;
  captureNumber: number;
  uploadId: string;
  capturedAt: string;
  originalFilename: string | null;
  color: string;
  points: WaterfallPoint3D[];
  peakCount: number;
}

export interface WaterfallAxisRanges {
  frequency: [number, number];
  capture: [number, number];
  amplitude: [number, number];
}

export interface WaterfallModel {
  lines: WaterfallLine[];
  peaks: WaterfallPeakPoint[];
  ranges: WaterfallAxisRanges;
  /** capture_number -> capture, for tooltips without re-scanning the array. */
  captureByNumber: Map<number, WaterfallCapture>;
  totalPoints: number;
  droppedPoints: number;
  labels: { x: string; y: string; z: string };
}

/**
 * Deterministic hue sweep. The golden angle keeps neighbouring captures far apart in
 * hue, and index-derived means a re-render never reshuffles the colours.
 * Colour encodes capture identity only — never severity.
 */
const HUE_START = 205; // starts on the SensoVibe blue
const GOLDEN_ANGLE = 137.508;

export function captureColor(index: number): string {
  const hue = (HUE_START + index * GOLDEN_ANGLE) % 360;
  const lightness = 42 + ((index * 7) % 14); // 42–56%, keeps every line readable on white
  return `hsl(${hue.toFixed(1)}, 62%, ${lightness}%)`;
}

function isFinitePair(frequency: number, amplitude: number): boolean {
  return Number.isFinite(frequency) && Number.isFinite(amplitude);
}

function buildLinePoints(
  capture: WaterfallCapture
): { points: WaterfallPoint3D[]; dropped: number } {
  const { frequencies, amplitudes, capture_number: z } = capture;
  const size = Math.min(frequencies.length, amplitudes.length);
  const points: WaterfallPoint3D[] = [];
  let dropped = 0;

  for (let i = 0; i < size; i += 1) {
    const frequency = frequencies[i];
    const amplitude = amplitudes[i];
    if (!isFinitePair(frequency, amplitude)) {
      dropped += 1;
      continue;
    }
    points.push([frequency, z, amplitude]);
  }
  return { points, dropped };
}

function buildPeakPoints(
  peaks: WaterfallPeak[],
  captureNumber: number,
  captureIndex: number
): WaterfallPeakPoint[] {
  const out: WaterfallPeakPoint[] = [];
  for (const peak of peaks) {
    if (!isFinitePair(peak.frequency, peak.amplitude)) continue;
    out.push({
      point: [peak.frequency, captureNumber, peak.amplitude],
      captureIndex,
    });
  }
  return out;
}

/** Fall back to the observed data range when the API could not supply bounds. */
function resolveRanges(
  data: WaterfallResponse,
  lines: WaterfallLine[]
): WaterfallAxisRanges {
  let fMin = data.frequency_min_hz;
  let fMax = data.frequency_max_hz;
  let aMin = data.amplitude_min;
  let aMax = data.amplitude_max;

  if (fMin == null || fMax == null || aMin == null || aMax == null) {
    let f0 = Number.POSITIVE_INFINITY;
    let f1 = Number.NEGATIVE_INFINITY;
    let a0 = Number.POSITIVE_INFINITY;
    let a1 = Number.NEGATIVE_INFINITY;
    for (const line of lines) {
      for (const [frequency, , amplitude] of line.points) {
        if (frequency < f0) f0 = frequency;
        if (frequency > f1) f1 = frequency;
        if (amplitude < a0) a0 = amplitude;
        if (amplitude > a1) a1 = amplitude;
      }
    }
    if (Number.isFinite(f0)) {
      fMin = fMin ?? f0;
      fMax = fMax ?? f1;
      aMin = aMin ?? a0;
      aMax = aMax ?? a1;
    }
  }

  const captureNumbers = lines.map((l) => l.captureNumber);
  return {
    frequency: [fMin ?? 0, fMax ?? 1],
    capture: [
      captureNumbers.length ? Math.min(...captureNumbers) : 1,
      captureNumbers.length ? Math.max(...captureNumbers) : 1,
    ],
    // Amplitude starts at 0 so relative peak height reads correctly across captures.
    amplitude: [Math.min(0, aMin ?? 0), aMax ?? 1],
  };
}

export function buildWaterfallModel(data: WaterfallResponse): WaterfallModel {
  const lines: WaterfallLine[] = [];
  const peaks: WaterfallPeakPoint[] = [];
  const captureByNumber = new Map<number, WaterfallCapture>();
  let totalPoints = 0;
  let droppedPoints = 0;

  data.captures.forEach((capture, index) => {
    const { points, dropped } = buildLinePoints(capture);
    droppedPoints += dropped;
    if (points.length < 2) return;

    captureByNumber.set(capture.capture_number, capture);
    totalPoints += points.length;
    peaks.push(...buildPeakPoints(capture.peaks, capture.capture_number, index));

    lines.push({
      captureIndex: index,
      captureNumber: capture.capture_number,
      uploadId: capture.upload_id,
      capturedAt: capture.captured_at,
      originalFilename: capture.original_filename,
      color: captureColor(index),
      points,
      peakCount: capture.peaks.length,
    });
  });

  return {
    lines,
    peaks,
    ranges: resolveRanges(data, lines),
    captureByNumber,
    totalPoints,
    droppedPoints,
    labels: { x: data.x_label, y: data.y_label, z: data.z_label },
  };
}
