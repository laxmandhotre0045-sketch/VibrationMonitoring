import type { PlotSeries } from "@/types/measurements";

/** Matches backend default when plot config is unavailable. */
export const DEFAULT_SAMPLE_RATE_HZ = 25600;

export interface TimeAxisDiagnostics {
  sampleCount: number;
  sampleRateHz: number;
  backendXLabel: string;
  backendFirstX: number | undefined;
  backendLastX: number | undefined;
  backendSpanSeconds: number | undefined;
  backendLooksLikeEpoch: boolean;
  generatedFirstMs: number;
  generatedLastMs: number;
  generatedSpanMs: number;
  expectedSpanMs: number;
  likelyDistorted: boolean;
}

function readMetadataSampleRate(metadata: Record<string, unknown>): number | undefined {
  const value = metadata.sampling_rate_hz;
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : undefined;
}

/** Resolve sample rate from plot metadata, page config, or default — no API changes. */
export function resolveSampleRateHz(plot: PlotSeries, configuredRateHz?: number): number {
  return (
    readMetadataSampleRate(plot.metadata) ??
    (configuredRateHz && configuredRateHz > 0 ? configuredRateHz : DEFAULT_SAMPLE_RATE_HZ)
  );
}

/** Frontend-generated relative time axis in milliseconds: t[i] = (i / sampleRate) × 1000. */
export function generateTimeAxisMs(sampleCount: number, sampleRateHz: number): number[] {
  if (sampleCount <= 0 || sampleRateHz <= 0) return [];
  return Array.from({ length: sampleCount }, (_, i) => (i / sampleRateHz) * 1000);
}

/** Chart pairs [timeMs, amplitude] — amplitudes are never modified. */
export function buildTimeWaveformChartPairs(
  amplitudes: number[],
  sampleRateHz: number
): [number, number][] {
  const timeAxisMs = generateTimeAxisMs(amplitudes.length, sampleRateHz);
  return amplitudes.map((value, i) => [timeAxisMs[i], value]);
}

/**
 * Replace unreliable backend timestamps with index-derived time (ms) for display only.
 * Original amplitude array is passed through unchanged.
 */
export function withGeneratedTimeAxis(
  plot: PlotSeries,
  configuredRateHz?: number
): PlotSeries {
  if (plot.plot_type !== "time_waveform") return plot;

  const sampleRateHz = resolveSampleRateHz(plot, configuredRateHz);
  const xMs = generateTimeAxisMs(plot.y.length, sampleRateHz);

  return {
    ...plot,
    x: xMs,
    x_label: "Time (ms)",
    metadata: {
      ...plot.metadata,
      sampling_rate_hz: sampleRateHz,
      time_axis_source: "frontend_index",
    },
  };
}

/** Compare backend X values vs expected index-based span (for diagnostics). */
export function analyzeTimeAxis(
  plot: PlotSeries,
  configuredRateHz?: number
): TimeAxisDiagnostics | null {
  if (plot.plot_type !== "time_waveform" || plot.y.length === 0) return null;

  const sampleRateHz = resolveSampleRateHz(plot, configuredRateHz);
  const sampleCount = plot.y.length;
  const generated = generateTimeAxisMs(sampleCount, sampleRateHz);
  const backend = plot.x;

  const backendFirstX = backend[0];
  const backendLastX = backend[backend.length - 1];
  const backendSpanSeconds =
    backend.length > 1 && backendFirstX !== undefined && backendLastX !== undefined
      ? backendLastX - backendFirstX
      : undefined;

  const expectedSpanMs = ((sampleCount - 1) / sampleRateHz) * 1000;
  const backendSpanMs =
    backendSpanSeconds !== undefined ? backendSpanSeconds * 1000 : undefined;

  const backendLooksLikeEpoch =
    backendFirstX !== undefined && Math.abs(backendFirstX) > 1e9;

  const spanMismatch =
    backendSpanMs !== undefined &&
    Math.abs(backendSpanMs - expectedSpanMs) > expectedSpanMs * 0.05;

  return {
    sampleCount,
    sampleRateHz,
    backendXLabel: plot.x_label,
    backendFirstX,
    backendLastX,
    backendSpanSeconds,
    backendLooksLikeEpoch,
    generatedFirstMs: generated[0],
    generatedLastMs: generated[generated.length - 1],
    generatedSpanMs: generated[generated.length - 1] - generated[0],
    expectedSpanMs,
    likelyDistorted: backendLooksLikeEpoch || spanMismatch || backend.length !== sampleCount,
  };
}

/** Readable millisecond labels for chart axes and tooltips. */
export function formatTimeMs(ms: number): string {
  if (!Number.isFinite(ms)) return "—";
  const abs = Math.abs(ms);
  if (abs < 0.01) return `${ms.toFixed(4)} ms`;
  if (abs < 1) return `${ms.toFixed(3)} ms`;
  if (abs < 100) return `${ms.toFixed(2)} ms`;
  return `${ms.toFixed(1)} ms`;
}
