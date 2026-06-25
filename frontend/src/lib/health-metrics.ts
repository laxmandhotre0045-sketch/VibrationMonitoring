import type { PlotSeries } from "@/types/measurements";
import type {
  HealthMetricKey,
  HealthMetricTrend,
  HealthStatusCardKey,
  HealthStatusLevel,
  HealthThresholdRow,
} from "@/types/health-status";
import { HEALTH_STATUS_CARD_KEYS } from "@/types/health-status";
import { getPlotThresholds } from "./chart-thresholds";
import { formatHealthMetricDisplay } from "./health-trend-option";

const SEGMENT_COUNT = 32;

const METRIC_CONFIG: Record<
  Exclude<HealthMetricKey, "temperature" | "battery_health">,
  { label: string; unit: string }
> = {
  rms: { label: "RMS", unit: "g" },
  vrms: { label: "VRMS", unit: "mm/s" },
  crest_factor: { label: "Crest", unit: "" },
  skew: { label: "Skew", unit: "" },
  kurtosis: { label: "Kurtosis", unit: "" },
  peak: { label: "Peak Value", unit: "g" },
  transients: { label: "Transients", unit: "g" },
  saturation: { label: "Saturation", unit: "%" },
};

function readMetaNumber(metadata: Record<string, unknown>, key: string): number | undefined {
  const value = metadata[key];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function mean(values: number[]): number {
  if (values.length === 0) return 0;
  return values.reduce((sum, v) => sum + v, 0) / values.length;
}

export function rms(values: number[]): number {
  if (values.length === 0) return 0;
  return Math.sqrt(mean(values.map((v) => v * v)));
}

export function peak(values: number[]): number {
  if (values.length === 0) return 0;
  return Math.max(...values.map((v) => Math.abs(v)));
}

export function crestFactor(values: number[]): number {
  const r = rms(values);
  if (r === 0) return 0;
  return peak(values) / r;
}

export function skewness(values: number[]): number {
  if (values.length < 3) return 0;
  const m = mean(values);
  const n = values.length;
  const sd = Math.sqrt(mean(values.map((v) => (v - m) ** 2)));
  if (sd === 0) return 0;
  const m3 = mean(values.map((v) => ((v - m) / sd) ** 3));
  return (n / ((n - 1) * (n - 2))) * m3 * (n - 1);
}

export function kurtosisExcess(values: number[]): number {
  if (values.length < 4) return 0;
  const m = mean(values);
  const n = values.length;
  const sd = Math.sqrt(mean(values.map((v) => (v - m) ** 2)));
  if (sd === 0) return 0;
  const m4 = mean(values.map((v) => ((v - m) / sd) ** 4));
  const k = (n * (n + 1)) / ((n - 1) * (n - 2) * (n - 3)) * m4;
  const correction = (3 * (n - 1) ** 2) / ((n - 2) * (n - 3));
  return k - correction;
}

function transientsG(values: number[]): number {
  if (values.length === 0) return 0;
  const m = mean(values);
  return Math.max(...values.map((v) => Math.abs(v - m)));
}

function saturationPercent(values: number[]): number {
  if (values.length === 0) return 0;
  const maxAbs = peak(values);
  if (maxAbs === 0) return 0;
  const clipLevel = maxAbs * 0.98;
  const clipped = values.filter((v) => Math.abs(v) >= clipLevel).length;
  return (clipped / values.length) * 100;
}

function velocityRmsMmPerS(accelerationG: number[], samplingRateHz: number): number {
  if (accelerationG.length < 2 || samplingRateHz <= 0) return 0;
  const dt = 1 / samplingRateHz;
  let velocity = 0;
  const velocities: number[] = [];
  for (const g of accelerationG) {
    velocity += g * 9.80665 * dt;
    velocities.push(velocity);
  }
  const meanV = mean(velocities);
  const centered = velocities.map((v) => v - meanV);
  return rms(centered) * 1000;
}

type SegmentMetricFn = (segment: number[], samplingRateHz: number) => number;

const SEGMENT_METRIC_FN: Record<
  Exclude<HealthMetricKey, "temperature" | "battery_health">,
  SegmentMetricFn
> = {
  rms: (segment) => rms(segment),
  vrms: (segment, rate) => velocityRmsMmPerS(segment, rate),
  crest_factor: (segment) => crestFactor(segment),
  skew: (segment) => skewness(segment),
  kurtosis: (segment) => kurtosisExcess(segment),
  peak: (segment) => peak(segment),
  transients: (segment) => transientsG(segment),
  saturation: (segment) => saturationPercent(segment),
};

function computeSegmentTrend(
  samples: number[],
  timeX: number[],
  samplingRateHz: number,
  metricFn: SegmentMetricFn
): { trendX: number[]; trendY: number[]; value: number } {
  const n = samples.length;
  const segmentSize = Math.max(1, Math.floor(n / SEGMENT_COUNT));
  const trendX: number[] = [];
  const trendY: number[] = [];

  for (let start = 0; start < n - segmentSize + 1; start += segmentSize) {
    const segment = samples.slice(start, start + segmentSize);
    trendY.push(metricFn(segment, samplingRateHz));
    const mid = start + Math.floor(segmentSize / 2);
    trendX.push(timeX[mid] ?? mid / samplingRateHz);
  }

  if (trendY.length === 0) {
    trendY.push(metricFn(samples, samplingRateHz));
    trendX.push(timeX[Math.floor(timeX.length / 2)] ?? 0);
  }

  return {
    trendX,
    trendY,
    value: trendY[trendY.length - 1] ?? metricFn(samples, samplingRateHz),
  };
}

function resolveStatus(
  value: number | null,
  warning?: number,
  danger?: number
): HealthStatusLevel {
  if (value === null || !Number.isFinite(value)) return "neutral";
  if (danger !== undefined && value >= danger) return "danger";
  if (warning !== undefined && value >= warning) return "warning";
  if (warning !== undefined || danger !== undefined) return "healthy";
  return "neutral";
}

function buildComputedMetric(
  key: Exclude<HealthMetricKey, "temperature" | "battery_health">,
  samples: number[],
  timeX: number[],
  samplingRateHz: number,
  thresholds: { warning?: number; danger?: number }
): HealthMetricTrend {
  const { label, unit } = METRIC_CONFIG[key];
  const { trendX, trendY, value } = computeSegmentTrend(
    samples,
    timeX,
    samplingRateHz,
    SEGMENT_METRIC_FN[key]
  );

  return {
    key,
    label,
    unit,
    value,
    trendX,
    trendY,
    available: samples.length > 0,
    status: resolveStatus(value, thresholds.warning, thresholds.danger),
    warningThreshold: thresholds.warning,
    dangerThreshold: thresholds.danger,
  };
}

function buildScalarMetric(
  key: "temperature" | "battery_health",
  label: string,
  unit: string,
  value: number | undefined,
  thresholds: { warning?: number; danger?: number }
): HealthMetricTrend {
  const available = value !== undefined;
  return {
    key,
    label,
    unit,
    value: available ? value : null,
    trendX: available ? [0, 1] : [],
    trendY: available && value !== undefined ? [value, value] : [],
    available,
    status: available
      ? resolveStatus(value ?? null, thresholds.warning, thresholds.danger)
      : "neutral",
    warningThreshold: thresholds.warning,
    dangerThreshold: thresholds.danger,
  };
}

function formatDelta(current: number | null, prior: number | null, unit: string): string {
  if (current === null || prior === null || !Number.isFinite(current) || !Number.isFinite(prior)) {
    return "—";
  }
  const delta = current - prior;
  const sign = delta > 0 ? "+" : "";
  return `${sign}${formatHealthMetricDisplay(delta, unit)}`;
}

function formatRange(values: number[], unit: string): string {
  const finite = values.filter((v) => Number.isFinite(v));
  if (finite.length === 0) return "—";
  const min = Math.min(...finite);
  const max = Math.max(...finite);
  return `${formatHealthMetricDisplay(min, unit)} – ${formatHealthMetricDisplay(max, unit)}`;
}

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

export function extractWaveformSamples(
  plots: PlotSeries[] | undefined,
  samplingRateHz: number
): { samples: number[]; timeX: number[] } | null {
  const waveform = plots?.find((p) => p.plot_type === "time_waveform");
  if (!waveform || waveform.y.length === 0) return null;
  const samples = waveform.y;
  const timeX =
    waveform.x.length === samples.length
      ? waveform.x
      : samples.map((_, i) => i / samplingRateHz);
  return { samples, timeX };
}

export function computeHealthMetrics(
  plots: PlotSeries[] | undefined,
  channel: number,
  samplingRateHz: number
): {
  metrics: HealthMetricTrend[];
  statusCardMetrics: HealthMetricTrend[];
  thresholdRows: HealthThresholdRow[];
  hasThresholds: boolean;
  bannerMessage: string;
  cautionThreshold?: number;
  warningThreshold?: number;
} {
  const waveform = plots?.find((p) => p.plot_type === "time_waveform");
  const trendPlot = plots?.find((p) => p.plot_type === "trend_plot");
  const metadata = waveform?.metadata ?? trendPlot?.metadata ?? {};
  const thresholds = getPlotThresholds(
    trendPlot ??
      waveform ?? {
        plot_type: "trend_plot",
        title: "",
        x_label: "",
        y_label: "",
        x: [],
        y: [],
        channel,
        metadata,
      }
  );

  const hasThresholds =
    thresholds.warning !== undefined || thresholds.danger !== undefined;

  const bannerMessage = hasThresholds
    ? "Thresholds loaded for this sensor/channel set. Health status reflects warning and danger limits."
    : "No thresholds saved for this sensor/channel set. Showing calculated trend only.";

  if (!waveform || waveform.y.length === 0) {
    return {
      metrics: [],
      statusCardMetrics: [],
      thresholdRows: [],
      hasThresholds,
      bannerMessage,
      cautionThreshold: thresholds.warning,
      warningThreshold: thresholds.danger,
    };
  }

  const samples = waveform.y;
  const timeX =
    waveform.x.length === samples.length
      ? waveform.x
      : samples.map((_, i) => i / samplingRateHz);

  const temperature =
    readMetaNumber(metadata, "temperature_c") ?? readMetaNumber(metadata, "temperature");
  const battery =
    readMetaNumber(metadata, "battery_health") ?? readMetaNumber(metadata, "battery_percent");

  const computedKeys = Object.keys(METRIC_CONFIG) as Array<
    Exclude<HealthMetricKey, "temperature" | "battery_health">
  >;

  const metrics: HealthMetricTrend[] = [
    ...computedKeys.map((key) =>
      buildComputedMetric(key, samples, timeX, samplingRateHz, thresholds)
    ),
    buildScalarMetric("temperature", "Temperature", "°C", temperature, thresholds),
    buildScalarMetric("battery_health", "Battery Health", "%", battery, thresholds),
  ];

  const statusCardMetrics = metrics.filter((m) =>
    HEALTH_STATUS_CARD_KEYS.includes(m.key as HealthStatusCardKey)
  );

  return {
    metrics,
    statusCardMetrics,
    thresholdRows: buildThresholdRows(statusCardMetrics),
    hasThresholds,
    bannerMessage,
    cautionThreshold: thresholds.warning,
    warningThreshold: thresholds.danger,
  };
}

export function computeScalarFromSamples(
  key: HealthMetricKey,
  samples: number[],
  samplingRateHz: number
): number | null {
  if (samples.length === 0) return null;
  if (key === "temperature" || key === "battery_health") return null;
  return SEGMENT_METRIC_FN[key](samples, samplingRateHz);
}
