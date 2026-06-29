export interface ChartStatistics {
  rms: number | null;
  peak: number | null;
  peakToPeak: number | null;
  mean: number | null;
  min: number | null;
  max: number | null;
  crestFactor: number | null;
  samplingRateHz: number | null;
  rpm: number | null;
  sensorStatus: string;
}

export interface ChartStatisticsContext {
  samplingRateHz?: number | null;
  rpm?: number | null;
  sensorStatus?: string | null;
}

function finiteValues(values: number[]): number[] {
  return values.filter((v) => Number.isFinite(v));
}

export function computeChartStatistics(
  values: number[],
  context: ChartStatisticsContext = {}
): ChartStatistics {
  const samples = finiteValues(values);
  if (samples.length === 0) {
    return {
      rms: null,
      peak: null,
      peakToPeak: null,
      mean: null,
      min: null,
      max: null,
      crestFactor: null,
      samplingRateHz: context.samplingRateHz ?? null,
      rpm: context.rpm ?? null,
      sensorStatus: context.sensorStatus ?? "—",
    };
  }

  const min = Math.min(...samples);
  const max = Math.max(...samples);
  const peak = Math.max(...samples.map(Math.abs));
  const mean = samples.reduce((sum, v) => sum + v, 0) / samples.length;
  const rms = Math.sqrt(samples.reduce((sum, v) => sum + v * v, 0) / samples.length);
  const peakToPeak = max - min;
  const crestFactor = rms > 0 ? peak / rms : null;

  return {
    rms,
    peak,
    peakToPeak,
    mean,
    min,
    max,
    crestFactor,
    samplingRateHz: context.samplingRateHz ?? null,
    rpm: context.rpm ?? null,
    sensorStatus: context.sensorStatus ?? "Online",
  };
}

export function sliceValuesByZoomPercent(
  values: number[],
  startPercent: number,
  endPercent: number
): number[] {
  if (values.length === 0) return [];
  const start = Math.max(0, Math.floor((startPercent / 100) * values.length));
  const end = Math.min(values.length, Math.ceil((endPercent / 100) * values.length));
  if (end <= start) return values;
  return values.slice(start, end);
}

export function formatStatValue(value: number | null, digits = 4): string {
  if (value === null || !Number.isFinite(value)) return "—";
  if (Math.abs(value) >= 1000) return value.toExponential(3);
  if (Math.abs(value) >= 1) return value.toFixed(digits);
  return value.toFixed(Math.min(digits + 2, 6));
}
