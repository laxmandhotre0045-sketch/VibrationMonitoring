import api from "./client";
import type {
  AllPlotsResponse,
  PlotConfig,
  PlotConfigInput,
  PlotSeries,
  SensorDataUpload,
} from "@/types/measurements";
import type { UploadFactorTrendsResponse } from "@/types/factor-trends";
import type { WaterfallQuery, WaterfallResponse } from "@/types/waterfall";
import type { VibrationVectorQuery, VibrationVectorResponse } from "@/types/vector";
import type { CasingOrbitQuery, CasingOrbitResponse } from "@/types/orbit";
import type { OneXMigrationQuery, OneXMigrationResponse } from "@/types/migration";
import type {
  RawAnalysisResponse,
  RawSamplesQuery,
  RawSamplesResponse,
  RawSnapshotListResponse,
} from "@/types/raw-vibration";
import type { FeatureCompareResponse, UploadFeaturesResponse } from "@/types/features";
import {
  normalizeFeatureCompareResponse,
  normalizeUploadFeaturesResponse,
} from "@/lib/feature-api-normalize";

/** Create or update plot config (backend upserts on POST). */
export async function configurePlots(data: PlotConfigInput): Promise<PlotConfig> {
  const res = await api.post("/api/v1/measurements/configure", data);
  return res.data;
}

export async function savePlotConfig(
  sensorId: string,
  data: PlotConfigInput,
  hasExisting?: boolean
): Promise<PlotConfig> {
  if (hasExisting) {
    const { sensor_id: _, ...update } = data;
    return updatePlotConfig(sensorId, update);
  }
  try {
    return await configurePlots(data);
  } catch (err: unknown) {
    const status = (err as { response?: { status?: number } })?.response?.status;
    if (status === 409) {
      const { sensor_id: _, ...update } = data;
      return updatePlotConfig(sensorId, update);
    }
    throw err;
  }
}

export async function getPlotConfig(sensorId: string): Promise<PlotConfig> {
  const res = await api.get(`/api/v1/measurements/configure/${sensorId}`);
  return res.data;
}

export async function updatePlotConfig(
  sensorId: string,
  data: Partial<Omit<PlotConfigInput, "sensor_id">>
): Promise<PlotConfig> {
  const res = await api.put(`/api/v1/measurements/configure/${sensorId}`, data);
  return res.data;
}

export async function uploadSensorPdf(
  sensorId: string,
  channelCount: number,
  file: File
): Promise<SensorDataUpload> {
  const form = new FormData();
  form.append("sensor_id", sensorId);
  form.append("channel_count", String(channelCount));
  form.append("file", file);
  const res = await api.post("/api/v1/measurements/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data;
}

export async function listUploads(
  sensorId: string,
  filters?: { fromDate?: string; toDate?: string; pageSize?: number }
): Promise<{ items: SensorDataUpload[]; total: number }> {
  const res = await api.get("/api/v1/measurements/uploads", {
    params: {
      sensor_id: sensorId,
      from_date: filters?.fromDate,
      to_date: filters?.toDate,
      page: 1,
      page_size: filters?.pageSize ?? 200,
    },
  });
  const data = res.data;
  if (Array.isArray(data)) {
    return { items: data, total: data.length };
  }
  return {
    items: data.items ?? [],
    total: typeof data.total === "number" ? data.total : (data.items ?? []).length,
  };
}

export async function getAllPlots(uploadId: string, channel?: number): Promise<AllPlotsResponse> {
  const res = await api.get(`/api/v1/measurements/uploads/${uploadId}/plots`, {
    params: channel !== undefined ? { channel } : undefined,
  });
  return res.data;
}

export async function getSinglePlot(
  uploadId: string,
  plotType: string,
  channel?: number
): Promise<PlotSeries> {
  const res = await api.get(`/api/v1/measurements/uploads/${uploadId}/plots/${plotType}`, {
    params: channel !== undefined ? { channel } : undefined,
  });
  return res.data;
}

export async function getPlotTypes(): Promise<string[]> {
  const res = await api.get("/api/v1/measurements/plot-types");
  return res.data.plot_types;
}

/** Stacked FFT spectra across captures for the 3D waterfall. */
export async function getWaterfall(query: WaterfallQuery): Promise<WaterfallResponse> {
  const res = await api.get("/api/v1/measurements/waterfall", {
    params: {
      sensor_id: query.sensorId,
      channel: query.channel,
      count: query.count,
      mode: query.mode,
      plot_type: query.plotType,
      ...(query.maxPoints !== undefined ? { max_points: query.maxPoints } : {}),
      ...(query.maxPeaks !== undefined ? { max_peaks: query.maxPeaks } : {}),
      ...(query.seed !== undefined ? { seed: query.seed } : {}),
    },
    timeout: 120_000,
  });
  return res.data;
}

/** Raw 25 kSPS snapshots stored for a sensor, newest first. */
export async function listRawSnapshots(
  sensorId: string,
  limit = 50
): Promise<RawSnapshotListResponse> {
  const res = await api.get("/api/v1/measurements/raw/snapshots", {
    params: { sensor_id: sensorId, limit },
  });
  return res.data;
}

/**
 * Raw samples of one snapshot, windowed.
 *
 * Always pass `channels` — one second of all eight channels is ~3.5 MB, while a single
 * channel is a fraction of that.
 */
export async function getRawSamples(query: RawSamplesQuery): Promise<RawSamplesResponse> {
  const res = await api.get(`/api/v1/measurements/uploads/${query.uploadId}/raw`, {
    params: {
      ...(query.offset !== undefined ? { offset: query.offset } : {}),
      ...(query.limit !== undefined ? { limit: query.limit } : {}),
      ...(query.channels?.length ? { channels: query.channels.join(",") } : {}),
    },
    timeout: 120_000,
  });
  return res.data;
}

/** Newest raw snapshot for a sensor, windowed. */
export async function getLatestRawSamples(
  sensorId: string,
  options: { offset?: number; limit?: number; channels?: number[] } = {}
): Promise<RawSamplesResponse> {
  const res = await api.get("/api/v1/measurements/raw/latest", {
    params: {
      sensor_id: sensorId,
      ...(options.offset !== undefined ? { offset: options.offset } : {}),
      ...(options.limit !== undefined ? { limit: options.limit } : {}),
      ...(options.channels?.length ? { channels: options.channels.join(",") } : {}),
    },
    timeout: 120_000,
  });
  return res.data;
}

/**
 * 1x amplitude migration: one point per capture, X = vertical 1x amplitude,
 * Y = horizontal 1x amplitude, each capture tracked at its own shaft frequency.
 */
export async function getOneXMigration(
  query: OneXMigrationQuery
): Promise<OneXMigrationResponse> {
  const res = await api.get("/api/v1/measurements/one-x-migration", {
    params: {
      sensor_id: query.sensorId,
      x_channel: query.xChannel,
      y_channel: query.yChannel,
      count: query.count,
      mode: query.mode,
    },
    timeout: 180_000,
  });
  return res.data;
}

/**
 * Casing orbit X(t) vs Y(t) from two synchronously-sampled channels of one capture.
 * Values are double-integrated displacement in micrometres.
 */
export async function getCasingOrbit(query: CasingOrbitQuery): Promise<CasingOrbitResponse> {
  const res = await api.get(`/api/v1/measurements/uploads/${query.uploadId}/orbit`, {
    params: {
      x_channel: query.xChannel,
      y_channel: query.yChannel,
      harmonic: query.harmonic,
      bandwidth_percent: query.bandwidthPercent,
      display_revolutions: query.displayRevolutions,
      include_unfiltered: query.includeUnfiltered,
      ...(query.filterRevolutions !== undefined
        ? { filter_revolutions: query.filterRevolutions }
        : {}),
    },
    timeout: 120_000,
  });
  return res.data;
}

/**
 * Amplitude + self-referenced phase at one frequency, block by block, for one capture.
 * Backed by a read-only endpoint that re-runs the FFT purely to keep the complex value.
 */
export async function getVibrationVector(
  query: VibrationVectorQuery
): Promise<VibrationVectorResponse> {
  const res = await api.get(
    `/api/v1/measurements/uploads/${query.uploadId}/vector`,
    {
      params: {
        channel: query.channel,
        ...(query.targetHz !== undefined ? { target_hz: query.targetHz } : {}),
        ...(query.blockSize !== undefined ? { block_size: query.blockSize } : {}),
        ...(query.overlap !== undefined ? { overlap: query.overlap } : {}),
      },
      timeout: 120_000,
    }
  );
  return res.data;
}

/**
 * Estimated shaft speed (Hz) for one capture/channel.
 *
 * Read raw rather than through getUploadFeatures: the normalizer drops feature metadata,
 * and estimated_shaft_hz lives in the 1X feature's metadata. This is a derived estimate
 * (largest FFT bin in the 5-120 Hz band), never a measured tachometer reading.
 * Returns null whenever the value is absent.
 */
export async function getEstimatedShaftHz(
  uploadId: string,
  channel: number
): Promise<number | null> {
  const res = await api.get(`/api/v1/measurements/uploads/${uploadId}/features`, {
    params: { channel },
    timeout: 30_000,
  });
  const items: Array<{ feature_code?: string; metadata?: Record<string, unknown> }> =
    res.data?.items ?? [];
  for (const item of items) {
    const value = item?.metadata?.estimated_shaft_hz;
    if (typeof value === "number" && Number.isFinite(value) && value > 0) return value;
  }
  return null;
}

export async function getUploadFactorTrends(
  uploadId: string,
  channel: number
): Promise<UploadFactorTrendsResponse> {
  const res = await api.get(`/api/v1/measurements/uploads/${uploadId}/factor-trends`, {
    params: { channel },
    timeout: 120_000,
  });
  return res.data;
}

export async function getUploadFeatures(
  uploadId: string,
  channel?: number
): Promise<UploadFeaturesResponse> {
  const res = await api.get(`/api/v1/measurements/uploads/${uploadId}/features`, {
    params: channel !== undefined ? { channel } : undefined,
    timeout: 120_000,
  });
  return normalizeUploadFeaturesResponse(res.data, { uploadId, channel: channel ?? 0 });
}

export async function compareUploadFeatures(
  uploadId: string,
  baselineId: string,
  channel?: number
): Promise<FeatureCompareResponse> {
  const res = await api.get(`/api/v1/measurements/uploads/${uploadId}/features/compare`, {
    params: {
      baseline_id: baselineId,
      ...(channel !== undefined ? { channel } : {}),
    },
  });
  return normalizeFeatureCompareResponse(res.data, {
    uploadId,
    channel: channel ?? 0,
    baselineId,
  });
}

/**
 * FFT spectrum and vibration statistics for one channel of one raw snapshot.
 *
 * Computed server-side by the platform's shared FFT and feature-extraction code
 * so the numbers agree with the other analysis tabs — the browser never runs its
 * own transform.
 */
export async function getRawAnalysis(query: {
  uploadId: string;
  channel?: number;
}): Promise<RawAnalysisResponse> {
  const res = await api.get(`/api/v1/measurements/uploads/${query.uploadId}/raw/analysis`, {
    params: { ...(query.channel !== undefined ? { channel: query.channel } : {}) },
    timeout: 120_000,
  });
  return res.data;
}

/** Same analysis for whichever snapshot arrived most recently. */
export async function getLatestRawAnalysis(query: {
  sensorId: string;
  channel?: number;
}): Promise<RawAnalysisResponse> {
  const res = await api.get(`/api/v1/measurements/raw/latest/analysis`, {
    params: {
      sensor_id: query.sensorId,
      ...(query.channel !== undefined ? { channel: query.channel } : {}),
    },
    timeout: 120_000,
  });
  return res.data;
}
