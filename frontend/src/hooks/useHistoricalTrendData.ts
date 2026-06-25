import { useMemo } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { format, subDays } from "date-fns";
import { getAllPlots, listUploads } from "@/api/measurements";
import { getBaselinePlots } from "@/api/baselines";
import {
  computeScalarFromSamples,
  extractWaveformSamples,
} from "@/lib/health-metrics";
import type { HealthMetricKey, HealthMetricTrend } from "@/types/health-status";
import { TREND_TAB_METRIC_KEYS } from "@/types/health-status";
import type { SensorDataUpload } from "@/types/measurements";

const METRIC_LABELS: Record<HealthMetricKey, { label: string; unit: string }> = {
  rms: { label: "RMS", unit: "g" },
  vrms: { label: "VRMS", unit: "mm/s" },
  crest_factor: { label: "Crest", unit: "" },
  skew: { label: "Skew", unit: "" },
  kurtosis: { label: "Kurtosis", unit: "" },
  peak: { label: "Peak", unit: "g" },
  transients: { label: "Transients", unit: "g" },
  saturation: { label: "Saturation", unit: "%" },
  temperature: { label: "Temperature", unit: "°C" },
  battery_health: { label: "Battery", unit: "%" },
};

function defaultRange() {
  const to = format(new Date(), "yyyy-MM-dd");
  const from = format(subDays(new Date(), 30), "yyyy-MM-dd");
  return { from, to };
}

interface UseHistoricalTrendDataOptions {
  sensorId: string;
  channel: number;
  samplingRateHz: number;
  fromDate?: string;
  toDate?: string;
  primaryBaselineId?: string | null;
  compareBaseline: boolean;
  enabled?: boolean;
}

export function useHistoricalTrendData({
  sensorId,
  channel,
  samplingRateHz,
  fromDate,
  toDate,
  primaryBaselineId,
  compareBaseline,
  enabled = true,
}: UseHistoricalTrendDataOptions) {
  const range = useMemo(() => {
    const defaults = defaultRange();
    return {
      fromDate: fromDate || defaults.from,
      toDate: toDate || defaults.to,
    };
  }, [fromDate, toDate]);

  const uploadsQuery = useQuery({
    queryKey: ["trend-uploads", sensorId, range.fromDate, range.toDate],
    queryFn: () =>
      listUploads(sensorId, {
        fromDate: range.fromDate,
        toDate: range.toDate,
        pageSize: 200,
      }),
    enabled: enabled && !!sensorId,
  });

  const uploads = uploadsQuery.data?.items ?? [];

  const plotQueries = useQueries({
    queries: uploads.map((upload) => ({
      queryKey: ["trend-upload-plots", upload.id, channel],
      queryFn: () => getAllPlots(upload.id, channel),
      enabled: enabled && !!sensorId && uploads.length > 0,
      staleTime: 60_000,
    })),
  });

  const baselineQuery = useQuery({
    queryKey: ["trend-baseline-plots", primaryBaselineId, channel],
    queryFn: () => getBaselinePlots(primaryBaselineId!, channel),
    enabled: enabled && compareBaseline && !!primaryBaselineId,
  });

  const trendMetrics = useMemo((): HealthMetricTrend[] => {
    const points: { upload: SensorDataUpload; values: Partial<Record<HealthMetricKey, number | null>> }[] =
      [];

    uploads.forEach((upload, index) => {
      const plots = plotQueries[index]?.data?.plots;
      const waveform = extractWaveformSamples(plots, samplingRateHz);
      if (!waveform) return;

      const metadata =
        plots?.find((p) => p.plot_type === "time_waveform")?.metadata ?? {};
      const temp =
        typeof metadata.temperature === "number" ? metadata.temperature :
        typeof metadata.temperature_c === "number" ? metadata.temperature_c : null;

      const values: Partial<Record<HealthMetricKey, number | null>> = {};
      for (const key of TREND_TAB_METRIC_KEYS) {
        if (key === "temperature") {
          values[key] = temp;
        } else {
          values[key] = computeScalarFromSamples(key, waveform.samples, samplingRateHz);
        }
      }
      points.push({ upload, values });
    });

    points.sort((a, b) => a.upload.created_at.localeCompare(b.upload.created_at));

    const trendX = points.map((p) => new Date(p.upload.created_at).getTime());

    let baselineValues: Partial<Record<HealthMetricKey, number | null>> = {};
    if (compareBaseline && baselineQuery.data) {
      const waveform = extractWaveformSamples(baselineQuery.data.plots, samplingRateHz);
      const metadata =
        baselineQuery.data.plots.find((p) => p.plot_type === "time_waveform")?.metadata ?? {};
      const temp =
        typeof metadata.temperature === "number" ? metadata.temperature :
        typeof metadata.temperature_c === "number" ? metadata.temperature_c : null;
      if (waveform) {
        for (const key of TREND_TAB_METRIC_KEYS) {
          if (key === "temperature") {
            baselineValues[key] = temp;
          } else {
            baselineValues[key] = computeScalarFromSamples(key, waveform.samples, samplingRateHz);
          }
        }
      }
    }

    return TREND_TAB_METRIC_KEYS.map((key) => {
      const { label, unit } = METRIC_LABELS[key];
      const trendY = points.map((p) => p.values[key] ?? null);
      const available = trendY.some((v) => v !== null && Number.isFinite(v));
      const latest = available
        ? (trendY.filter((v) => v !== null).at(-1) ?? null)
        : null;

      const baselineValue = baselineValues[key];
      const displayTrendY =
        compareBaseline && baselineValue !== null && baselineValue !== undefined
          ? [...trendY, baselineValue]
          : trendY;
      const displayTrendX =
        compareBaseline && baselineValue !== null && baselineValue !== undefined
          ? [...trendX, trendX[trendX.length - 1] ?? Date.now()]
          : trendX;

      return {
        key,
        label: compareBaseline && baselineValue !== null && baselineValue !== undefined
          ? `${label} Trend (incl. baseline)`
          : `${label} Trend`,
        unit,
        value: latest,
        trendX: displayTrendX,
        trendY: displayTrendY.map((v) => v ?? 0),
        available,
        status: "neutral" as const,
      };
    });
  }, [
    uploads,
    plotQueries,
    samplingRateHz,
    compareBaseline,
    baselineQuery.data,
  ]);

  const isLoading =
    uploadsQuery.isLoading || plotQueries.some((q) => q.isLoading) ||
    (compareBaseline && baselineQuery.isLoading);

  return {
    range,
    uploads,
    trendMetrics,
    isLoading,
    uploadsQuery,
  };
}
