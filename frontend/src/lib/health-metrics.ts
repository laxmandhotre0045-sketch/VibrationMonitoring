/**
 * Presentation helpers for the health screens.
 *
 * This module used to compute vibration metrics in the browser — RMS, crest
 * factor, kurtosis, excess skew, velocity RMS, saturation and a 32-segment
 * trend — from whatever waveform the plots endpoint happened to return, and
 * screens used those numbers when the API returned none. That meant a value on
 * screen could have come from the analysis engine or from a second, unversioned
 * implementation here, with nothing to say which. A finding could not be traced
 * to one source and no evidence was auditable.
 *
 * Those implementations are gone. Everything measured now comes from the
 * backend, and a feature the API has not computed is shown as absent rather
 * than filled in locally. What remains here is formatting and labelling, which
 * describe nothing about the signal.
 */
import type { HealthMetricTrend, HealthThresholdRow } from "@/types/health-status";
import { formatHealthMetricDisplay } from "./health-trend-option";

function formatDelta(current: number | null, prior: number | null, unit: string): string {
  if (current === null || prior === null) return "—";
  const delta = current - prior;
  const sign = delta > 0 ? "+" : "";
  return `${sign}${formatHealthMetricDisplay(delta, unit)}`;
}

function formatRange(values: number[], unit: string): string {
  const usable = values.filter((value) => Number.isFinite(value));
  if (usable.length === 0) return "—";
  const min = Math.min(...usable);
  const max = Math.max(...usable);
  return `${formatHealthMetricDisplay(min, unit)} – ${formatHealthMetricDisplay(max, unit)}`;
}

/**
 * One table row per metric, formatted for display.
 *
 * Reads values the caller already has; it computes no metric of its own. The
 * arithmetic here is on numbers the engine produced — a difference between two
 * of its readings, and the span of a series of them.
 */
export function buildThresholdRows(metrics: HealthMetricTrend[]): HealthThresholdRow[] {
  return metrics
    .filter((m) => m.available)
    .map((metric) => {
      const prior =
        metric.trendY.length > 1 ? metric.trendY[metric.trendY.length - 2] : null;
      return {
        parameter: metric.unit ? `${metric.label} (${metric.unit})` : metric.label,
        latest: formatHealthMetricDisplay(metric.value, metric.unit),
        deltaVsPrior: formatDelta(metric.value, prior, metric.unit),
        rangePeriod: formatRange(metric.trendY, metric.unit),
        cautionLimit:
          metric.warningThreshold !== undefined
            ? formatHealthMetricDisplay(metric.warningThreshold, metric.unit)
            : "—",
        warningLimit:
          metric.dangerThreshold !== undefined
            ? formatHealthMetricDisplay(metric.dangerThreshold, metric.unit)
            : "—",
        status: metric.status,
      };
    });
}

export function channelLabel(channelIndex: number): string {
  return `CH-${channelIndex + 1}`;
}
