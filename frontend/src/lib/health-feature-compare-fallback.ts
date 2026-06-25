import type { PlotSeries } from "@/types/measurements";
import type { FeatureCompareItem, FeatureMonitorStatus } from "@/types/features";
import { HEALTH_STATUS_CARD_KEYS } from "@/types/health-status";
import { getPlotThresholds } from "./chart-thresholds";
import {
  computeScalarFromSamples,
  extractWaveformSamples,
} from "./health-metrics";

const COMPARE_METRICS: {
  key: (typeof HEALTH_STATUS_CARD_KEYS)[number];
  label: string;
  unit: string;
}[] = [
  { key: "rms", label: "RMS", unit: "g" },
  { key: "vrms", label: "VRMS", unit: "mm/s" },
  { key: "skew", label: "Skew", unit: "" },
  { key: "crest_factor", label: "Crest", unit: "" },
  { key: "transients", label: "Transients", unit: "g" },
  { key: "saturation", label: "Saturation", unit: "%" },
  { key: "temperature", label: "Temperature", unit: "°C" },
];

function resolveCompareStatus(
  uploadValue: number | null,
  baselineValue: number | null,
  warning?: number,
  danger?: number
): FeatureMonitorStatus {
  if (uploadValue === null || !Number.isFinite(uploadValue)) return "no_baseline";
  if (baselineValue === null || !Number.isFinite(baselineValue)) return "no_baseline";

  if (danger !== undefined && uploadValue >= danger) return "critical";
  if (warning !== undefined && uploadValue >= warning) return "warning";

  if (baselineValue === 0) {
    return Math.abs(uploadValue) < 0.001 ? "normal" : "warning";
  }

  const pct = Math.abs(((uploadValue - baselineValue) / baselineValue) * 100);
  if (pct >= 50) return "critical";
  if (pct >= 15) return "warning";
  return "normal";
}

function readTemperature(plots: PlotSeries[] | undefined): number | null {
  const metadata =
    plots?.find((p) => p.plot_type === "time_waveform")?.metadata ??
    plots?.[0]?.metadata ??
    {};
  const temp = metadata.temperature_c ?? metadata.temperature;
  return typeof temp === "number" && Number.isFinite(temp) ? temp : null;
}

export function buildCompareItemsFromPlots(
  uploadPlots: PlotSeries[] | undefined,
  baselinePlots: PlotSeries[] | undefined,
  samplingRateHz: number
): FeatureCompareItem[] {
  const uploadWaveform = extractWaveformSamples(uploadPlots, samplingRateHz);
  const baselineWaveform = extractWaveformSamples(baselinePlots, samplingRateHz);

  if (!uploadWaveform) return [];

  const trendPlot = uploadPlots?.find((p) => p.plot_type === "trend_plot");
  const thresholds = getPlotThresholds(
    trendPlot ??
      uploadPlots?.find((p) => p.plot_type === "time_waveform") ?? {
        plot_type: "trend_plot",
        title: "",
        x_label: "",
        y_label: "",
        x: [],
        y: [],
        channel: 0,
        metadata: {},
      }
  );

  return COMPARE_METRICS.map(({ key, label, unit }) => {
    let uploadValue: number | null;
    let baselineValue: number | null;

    if (key === "temperature") {
      uploadValue = readTemperature(uploadPlots);
      baselineValue = readTemperature(baselinePlots);
    } else {
      uploadValue = computeScalarFromSamples(key, uploadWaveform.samples, samplingRateHz);
      baselineValue = baselineWaveform
        ? computeScalarFromSamples(key, baselineWaveform.samples, samplingRateHz)
        : null;
    }

    const difference_percent =
      uploadValue !== null &&
      baselineValue !== null &&
      Number.isFinite(uploadValue) &&
      Number.isFinite(baselineValue) &&
      baselineValue !== 0
        ? ((uploadValue - baselineValue) / baselineValue) * 100
        : null;

    return {
      feature: unit ? `${label} (${unit})` : label,
      upload_value: uploadValue,
      baseline_value: baselineValue,
      difference_percent,
      status: resolveCompareStatus(
        uploadValue,
        baselineValue,
        thresholds.warning,
        thresholds.danger
      ),
      unit,
    };
  }).filter((item) => item.upload_value !== null);
}
