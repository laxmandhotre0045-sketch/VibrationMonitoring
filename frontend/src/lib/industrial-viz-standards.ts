/**
 * Industrial vibration visualization standards — display-only conventions.
 *
 * Primary references (uploaded reference library):
 * - Condition Monitoring with Vibration Signals (Randall/Antoni):
 *   alarm zone colour coding, harmonic/order markers, waveform symmetry, severity bands.
 * - The Scientist and Engineer's Guide to Digital Signal Processing (Smith):
 *   FFT frequency axis (Hz), Nyquist limit (fs/2), frequency resolution Δf = fs/N.
 * - ISO 10816 (machine vibration severity):
 *   velocity RMS zones are machine-class specific — never hard-coded here; use settings/metadata.
 *
 * All alarm thresholds and ISO zone limits must be supplied via plot metadata or the
 * Vibration Settings module so different machine types remain configurable.
 */

import type { PlotType } from "@/types/measurements";

/** Grid divisions used across diagnostic charts (typical CM software: 4–6 major divisions). */
export const INDUSTRIAL_AXIS_GRID = {
  splitNumber: 5,
  minorSplitLine: { show: false as const },
} as const;

/** Trace colours aligned with industrial CM software conventions. */
export const INDUSTRIAL_TRACE_COLORS: Record<PlotType, string> = {
  time_waveform: "#15366D",
  circular_time_waveform: "#15366D",
  fft_spectrum: "#D98C00",
  envelope_spectrum: "#C2410C",
  trend_plot: "#D98C00",
};

/** Reference line styles for non-alarm markers (Nyquist, harmonics, dominant peak). */
export const INDUSTRIAL_REFERENCE_LINE = {
  nyquist: {
    color: "#5C6B7A",
    type: "dashed" as const,
    width: 1,
    opacity: 0.75,
    label: "Nyquist",
  },
  harmonic: {
    color: "#15366D",
    type: "dotted" as const,
    width: 1,
    opacity: 0.55,
  },
  dominant: {
    color: "#FF6B00",
    type: "solid" as const,
    width: 1,
    opacity: 0.7,
  },
} as const;

/**
 * ISO 10816-3 velocity severity zones (mm/s RMS) — documented for future configuration.
 * Values vary by machine support class (Group 1–4). Do NOT auto-apply without asset config.
 */
export const ISO_10816_VELOCITY_ZONES_REFERENCE = {
  standard: "ISO 10816-3",
  note: "Zone limits depend on machine class and mounting. Configure per asset in Vibration Settings.",
  /** Example Group 2 rigid foundation (illustrative — configure per asset). */
  group2RigidExample: {
    zoneA: { max: 1.12, label: "Zone A — Good" },
    zoneB: { max: 2.8, label: "Zone B — Satisfactory" },
    zoneC: { max: 7.1, label: "Zone C — Unsatisfactory" },
    zoneD: { label: "Zone D — Unacceptable" },
  },
} as const;

/** Crest factor interpretation guide (display hints only — not alarm thresholds). */
export const CREST_FACTOR_DISPLAY_GUIDE = {
  reference: "Condition Monitoring with Vibration Signals",
  note: "Crest factor ≈ 3 for Gaussian signals; elevated values may indicate impulsive faults.",
  gaussianReference: 3.0,
} as const;

/** Kurtosis interpretation guide (display hints only). */
export const KURTOSIS_DISPLAY_GUIDE = {
  reference: "Condition Monitoring with Vibration Signals",
  note: "Kurtosis ≈ 3 for Gaussian noise; higher values suggest impulsive/spiky vibration.",
  gaussianReference: 3.0,
} as const;

export interface VizDisplayContext {
  sampleRateHz?: number | null;
  fftLines?: number | null;
  rpm?: number | null;
  yUnit?: string;
  sampleCount?: number | null;
}

/** Nyquist frequency = sampleRate / 2 (Smith, DSP Guide — Ch. 3–4). */
export function nyquistFrequencyHz(sampleRateHz: number): number {
  return sampleRateHz / 2;
}

/** Frequency resolution Δf = fs / N (Smith, DSP Guide — FFT chapter). */
export function frequencyResolutionHz(sampleRateHz: number, fftSize: number): number {
  if (fftSize <= 0) return 0;
  return sampleRateHz / fftSize;
}

/** Running speed in Hz from RPM. */
export function rpmToHz(rpm: number): number {
  return rpm / 60;
}

/** Parse unit token from plot axis label, e.g. "Amplitude (g)" → "g". */
export function parseUnitFromAxisLabel(axisLabel: string): string {
  const match = axisLabel.match(/\(([^)]+)\)/);
  return match?.[1]?.trim() ?? "";
}

/** Format amplitude with engineering unit suffix for tooltips and statistics. */
export function formatAmplitudeWithUnit(value: number, unit?: string): string {
  if (!Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  let formatted: string;
  if (abs >= 1000) formatted = value.toExponential(3);
  else if (abs >= 1) formatted = value.toFixed(4);
  else if (abs >= 0.001) formatted = value.toFixed(6);
  else formatted = value.toExponential(3);
  return unit ? `${formatted} ${unit}` : formatted;
}

export function readMetadataNumber(
  metadata: Record<string, unknown> | undefined,
  keys: string[]
): number | null {
  if (!metadata) return null;
  for (const key of keys) {
    const value = metadata[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
  }
  return null;
}

export function buildVizContextFromPlot(
  metadata: Record<string, unknown> | undefined,
  yLabel: string,
  sampleRateHz?: number | null,
  sampleCount?: number | null
): VizDisplayContext {
  return {
    sampleRateHz:
      sampleRateHz ??
      readMetadataNumber(metadata, ["sampling_rate_hz", "sample_rate_hz"]),
    fftLines: readMetadataNumber(metadata, ["fft_lines", "n_fft", "fft_size"]),
    rpm: readMetadataNumber(metadata, ["rpm", "speed_rpm", "shaft_rpm", "rated_rpm"]),
    yUnit: parseUnitFromAxisLabel(yLabel),
    sampleCount,
  };
}
