/**
 * Vector API response -> polar-ready model.
 *
 * ECharts polar series take each datum as [radius, angle] — NOT [x, y]. Radius carries
 * the real FFT amplitude in engineering units; angle carries the self-referenced phase
 * in degrees. The physical amplitude is never scaled or normalised away.
 */
import { traceRampColor } from "./cascade-chart-option";
import type { VibrationVectorResponse } from "@/types/vector";

/** [radius, angle] exactly as ECharts polar expects. */
export type PolarPoint = [number, number];

export interface VectorPoint {
  blockIndex: number;
  timeS: number;
  /** Real FFT magnitude in `amplitudeUnit`. */
  amplitude: number;
  phaseDeg: number;
  relativePhaseDeg: number;
  isReference: boolean;
  isLatest: boolean;
  color: string;
  point: PolarPoint;
}

export interface PolarVectorModel {
  points: VectorPoint[];
  /** Path through every block tip, in block order. */
  path: PolarPoint[];
  /** Origin -> latest tip, drawn as the current vector. */
  latestVector: PolarPoint[];
  reference: VectorPoint | null;
  latest: VectorPoint | null;
  radiusMax: number;
  amplitudeUnit: string;
  /** False when every block is flat zero — the UI explains rather than drawing nothing. */
  hasSignificantAmplitude: boolean;
  /** Estimated shaft speed in RPM. Always label as estimated. */
  estimatedRpm: number | null;
}

/** Headroom so the outermost tip is not glued to the rim. */
const RADIUS_HEADROOM = 1.15;

export function buildPolarVectorModel(data: VibrationVectorResponse): PolarVectorModel {
  const blocks = data.blocks.filter(
    (b) => Number.isFinite(b.amplitude) && Number.isFinite(b.relative_phase_deg)
  );
  const total = blocks.length;

  const points: VectorPoint[] = blocks.map((b, index) => ({
    blockIndex: b.block_index,
    timeS: b.time_s,
    amplitude: b.amplitude,
    phaseDeg: b.phase_deg,
    relativePhaseDeg: b.relative_phase_deg,
    isReference: b.is_reference,
    isLatest: index === total - 1,
    // Reuse the cascade ramp so "older = lighter" reads the same across the app.
    color: traceRampColor(index, total),
    point: [b.amplitude, b.relative_phase_deg],
  }));

  const amplitudeMax = points.reduce((max, p) => Math.max(max, p.amplitude), 0);
  const latest = points.length ? points[points.length - 1] : null;
  const reference = points.find((p) => p.isReference) ?? null;

  return {
    points,
    path: points.map((p) => p.point),
    // Radius 0 at the latest angle keeps the vector pointing the right way from origin.
    latestVector: latest ? [[0, latest.relativePhaseDeg], latest.point] : [],
    reference,
    latest,
    // Scale from the data, never hard-coded; falls back to 1 so an all-zero capture
    // still renders a sane grid instead of collapsing.
    radiusMax: amplitudeMax > 0 ? amplitudeMax * RADIUS_HEADROOM : 1,
    amplitudeUnit: data.amplitude_unit,
    hasSignificantAmplitude: amplitudeMax > 0,
    estimatedRpm: data.estimated_shaft_hz != null ? data.estimated_shaft_hz * 60 : null,
  };
}
